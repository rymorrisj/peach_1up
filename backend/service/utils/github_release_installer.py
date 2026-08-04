"""Install a portable emulator from its latest GitHub release asset.

Sibling to ``emulator_installer.py``. Given an emulator slug whose catalog
entry declares ``install_type = "github_release"``, this module:

  1. Resolves the GitHub owner/repo from the entry's ``source_url``.
  2. Fetches the repo's latest release from the GitHub REST API.
  3. Matches the entry's ``asset_pattern`` (a regex) against the release
     asset names — failing loud on zero or multiple matches.
  4. Downloads the matched asset to a temporary location, fully, before any
     extraction begins.
  5. Computes the SHA256 of the download and compares it against the asset's
     ``digest`` field when GitHub provides one (assets published before
     June 2025 have a null digest — the check is skipped and noted).
  6. Extracts the archive into ``emulators/<slug>/`` with a zip-slip
     path-traversal guard.
  7. Ensures the portable sentinel file exists post-extraction.
  8. Records the install in the ``emulator_installs`` table.

Every step fails loud — there is no silent fallback. Temporary files are
removed on any failure.

Security-sensitive: this downloads and extracts an executable archive to disk
based on runtime API data. The zip-slip guard and the ``.git`` component
rejection are load-bearing; do not relax them.
"""

from __future__ import annotations

import hashlib
import re
import shutil
import subprocess
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import httpx

from backend.core.settings import get_base_path
from backend.service.utils.emulator_catalog import ensure_portable_mode, get_emulator

_BASE_DIR = get_base_path() / "emulators"
_SEVENZ_EXE = get_base_path() / "services" / "vendor" / "7z" / "7za.exe"
_API_ROOT = "https://api.github.com"
_API_TIMEOUT = 30.0
_DOWNLOAD_TIMEOUT = 300.0
_DOWNLOAD_CHUNK = 1024 * 1024  # 1 MiB
# RPCS3's win64_msvc build decompresses to ~143 MiB (149996575 bytes,
# confirmed by extracting the live release with 7za.exe), compressed size is
# ~35 MiB. PCSX2's Qt build is similar, ~140 MiB extracted from a ~27 MiB
# archive (config/emulators/pcsx2.toml). 500 MiB leaves headroom for growth
# while still bounding decompression-bomb archives.
_MAX_7Z_EXTRACT_SIZE = 500 * 1024 * 1024
_GITHUB_HEADERS = {
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
    "User-Agent": "peach1up-emulator-installer",
}

_SOURCE_URL_RE = re.compile(
    r"^https?://github\.com/(?P<owner>[^/]+)/(?P<repo>[^/]+?)(?:\.git)?/?$"
)


def _parse_owner_repo(source_url: str) -> tuple[str, str]:
    """Derive (owner, repo) from a GitHub ``source_url``.

    Raises:
        ValueError: If the URL is not a recognizable github.com repo URL.
    """
    m = _SOURCE_URL_RE.match((source_url or "").strip())
    if not m:
        raise ValueError(
            f"Cannot derive GitHub owner/repo from source_url {source_url!r}."
        )
    return m.group("owner"), m.group("repo")


def _fetch_latest_release(owner: str, repo: str) -> dict:
    """Fetch the latest published release for owner/repo from the GitHub API.

    Raises:
        RuntimeError: On any non-2xx response.
    """
    url = f"{_API_ROOT}/repos/{owner}/{repo}/releases/latest"
    with httpx.Client(timeout=_API_TIMEOUT, follow_redirects=True) as client:
        resp = client.get(url, headers=_GITHUB_HEADERS)
    if resp.status_code != 200:
        raise RuntimeError(
            f"GitHub API returned {resp.status_code} for {owner}/{repo} latest "
            f"release: {resp.text[:300]}"
        )
    return resp.json()


def _select_asset(release: dict, asset_pattern: str) -> dict:
    """Return the single release asset whose name matches ``asset_pattern``.

    Raises:
        RuntimeError: If zero or more than one asset matches — the match must
            be unambiguous.
    """
    pattern = re.compile(asset_pattern)
    assets = release.get("assets") or []
    matches = [a for a in assets if pattern.fullmatch(a.get("name", ""))]
    if not matches:
        available = ", ".join(a.get("name", "") for a in assets) or "<none>"
        raise RuntimeError(
            f"No release asset matched pattern {asset_pattern!r}. "
            f"Available assets: {available}"
        )
    if len(matches) > 1:
        names = ", ".join(a.get("name", "") for a in matches)
        raise RuntimeError(
            f"Multiple release assets matched pattern {asset_pattern!r}: {names}. "
            "Refusing to install an ambiguous asset."
        )
    return matches[0]


def _download_asset(download_url: str, dest: Path) -> None:
    """Stream ``download_url`` to ``dest``, completing fully before returning.

    Raises:
        RuntimeError: On any non-2xx response.
    """
    with httpx.Client(timeout=_DOWNLOAD_TIMEOUT, follow_redirects=True) as client:
        with client.stream("GET", download_url, headers=_GITHUB_HEADERS) as resp:
            if resp.status_code != 200:
                raise RuntimeError(
                    f"Asset download failed with HTTP {resp.status_code} for "
                    f"{download_url}."
                )
            with open(dest, "wb") as fh:
                for chunk in resp.iter_bytes(_DOWNLOAD_CHUNK):
                    fh.write(chunk)


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(_DOWNLOAD_CHUNK), b""):
            h.update(chunk)
    return h.hexdigest()


def _verify_digest(asset: dict, computed_sha256: str) -> bool:
    """Compare ``computed_sha256`` against the asset's ``digest`` field.

    Returns True if the digest was present and verified, False if the digest
    was absent (pre-June-2025 asset) and the check was skipped.

    Raises:
        RuntimeError: If the digest is present but uses an unexpected algorithm
            or does not match.
    """
    digest = asset.get("digest")
    if not digest:
        return False
    algo, sep, expected = digest.partition(":")
    if not sep:
        # Bare hex with no algorithm prefix — treat as sha256.
        algo, expected = "sha256", digest
    if algo.lower() != "sha256":
        raise RuntimeError(
            f"Asset {asset.get('name')!r} declares an unexpected digest "
            f"algorithm {algo!r}; refusing to install."
        )
    if expected.lower() != computed_sha256.lower():
        raise RuntimeError(
            f"SHA256 mismatch for asset {asset.get('name')!r}: "
            f"expected {expected}, computed {computed_sha256}."
        )
    return True


def _safe_extract_zip(zip_path: Path, dest_dir: Path) -> None:
    """Extract ``zip_path`` into ``dest_dir`` with a zip-slip guard.

    Each member's resolved destination is confirmed to stay within
    ``dest_dir`` before anything is written (same class of check used in the
    P-META cover-art download). Members whose path contains a ``.git``
    component are rejected — the repo's standing rule allows only the root
    ``.git``.

    Raises:
        RuntimeError: On any path that escapes ``dest_dir`` or carries a
            ``.git`` component.
    """
    dest_root = dest_dir.resolve()
    with zipfile.ZipFile(zip_path) as zf:
        for member in zf.infolist():
            name = member.filename
            if ".git" in Path(name).parts:
                raise RuntimeError(
                    f"Refusing to extract {name!r}: contains a '.git' path "
                    "component."
                )
            target = (dest_root / name).resolve()
            try:
                target.relative_to(dest_root)
            except ValueError:
                raise RuntimeError(
                    f"Zip-slip detected: {name!r} escapes {dest_root}."
                )
            if member.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(member) as src, open(target, "wb") as dst:
                shutil.copyfileobj(src, dst)


def _run_7za(args: list[str]) -> subprocess.CompletedProcess:
    """Run the vendored 7za.exe with an explicit argument list.

    Never uses ``shell=True`` or string-interpolated commands, arguments are
    passed as a list so no shell parses them.

    Raises:
        RuntimeError: If 7za.exe is missing from its vendored location.
    """
    if not _SEVENZ_EXE.is_file():
        raise RuntimeError(f"Vendored 7-Zip binary not found at {_SEVENZ_EXE}.")
    return subprocess.run(
        [str(_SEVENZ_EXE), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def _list_7z_entries(archive_path: Path) -> list[dict[str, str]]:
    """Return the parsed ``-slt`` (technical listing) entries of a .7z archive.

    Each entry is a dict of its ``Key = Value`` fields, keyed on 7za.exe's own
    field names (``Path``, ``Size``, ``Attributes``, ...). 7za.exe's ``-slt``
    output starts with a block describing the archive file itself, that block
    is not a member and is skipped by splitting on the ``----------``
    separator line 7za.exe prints before the member list.

    Raises:
        RuntimeError: On any non-zero 7za.exe exit code.
    """
    result = _run_7za(["l", "-slt", "-sccUTF-8", "--", str(archive_path)])
    if result.returncode != 0:
        raise RuntimeError(
            f"7za list failed (exit {result.returncode}) for {archive_path}: "
            f"{result.stderr.strip() or result.stdout.strip()}"
        )
    _, _, members_text = result.stdout.partition("----------")
    entries: list[dict[str, str]] = []
    for block in members_text.split("\n\n"):
        fields: dict[str, str] = {}
        for line in block.splitlines():
            key, sep, value = line.partition(" = ")
            if sep:
                fields[key.strip()] = value.strip()
        if "Path" in fields:
            entries.append(fields)
    return entries


def _safe_extract_7z(archive_path: Path, dest_dir: Path) -> None:
    """Extract ``archive_path`` (a .7z archive) into ``dest_dir`` using the
    vendored 7za.exe, with the same safety posture as ``_safe_extract_zip``.

    Every entry's path is resolved and confirmed to stay within ``dest_dir``,
    and entries with a ``.git`` path component are rejected, before 7za.exe
    is ever invoked to extract, same guard logic as ``_safe_extract_zip``.
    7za.exe has no built-in decompression-bomb size limit, so the archive's
    total uncompressed size (summed from the ``-slt`` listing) is checked
    against ``_MAX_7Z_EXTRACT_SIZE`` in the same pre-extraction pass.

    Raises:
        RuntimeError: On any path that escapes ``dest_dir``, a ``.git`` path
            component, a total uncompressed size over
            ``_MAX_7Z_EXTRACT_SIZE``, or any non-zero 7za.exe exit code.
    """
    dest_root = dest_dir.resolve()
    entries = _list_7z_entries(archive_path)

    total_size = 0
    for entry in entries:
        # 7za.exe reports paths with backslashes regardless of host OS, since
        # the archives it lists are always Windows-built.
        name = entry["Path"].replace("\\", "/")
        if ".git" in Path(name).parts:
            raise RuntimeError(
                f"Refusing to extract {name!r}: contains a '.git' path "
                "component."
            )
        target = (dest_root / name).resolve()
        try:
            target.relative_to(dest_root)
        except ValueError:
            raise RuntimeError(f"Zip-slip detected: {name!r} escapes {dest_root}.")
        if "D" not in entry.get("Attributes", ""):
            total_size += int(entry.get("Size") or 0)

    if total_size > _MAX_7Z_EXTRACT_SIZE:
        raise RuntimeError(
            f"7z extraction aborted: total uncompressed size {total_size} "
            f"bytes exceeds limit of {_MAX_7Z_EXTRACT_SIZE} bytes."
        )

    result = _run_7za(["x", "-y", f"-o{dest_root}", "--", str(archive_path)])
    if result.returncode != 0:
        raise RuntimeError(
            f"7za extraction failed (exit {result.returncode}) for "
            f"{archive_path}: {result.stderr.strip() or result.stdout.strip()}"
        )


def _record_install(
    slug: str,
    version: str,
    install_path: str,
    asset_filename: str,
    asset_url: str,
    sha256_digest: str,
    digest_verified: bool,
) -> None:
    """Insert or update the ``emulator_installs`` row for ``slug``."""
    from sqlalchemy.orm import sessionmaker

    from backend.core.database import get_engine
    from backend.models import EmulatorInstall

    now = datetime.now(timezone.utc)
    session_factory = sessionmaker(bind=get_engine())
    with session_factory() as db:
        row = (
            db.query(EmulatorInstall)
            .filter(EmulatorInstall.slug == slug)
            .one_or_none()
        )
        if row is None:
            row = EmulatorInstall(slug=slug, installed_version=version)
            db.add(row)
        row.installed_version = version
        row.installed_at = now
        row.install_path = install_path
        row.asset_filename = asset_filename
        row.asset_url = asset_url
        row.sha256_digest = sha256_digest
        row.digest_verified = digest_verified
        row.latest_known_version = version
        row.last_checked_at = now
        db.commit()


def install_from_github_release(slug: str) -> dict:
    """Download and install ``slug`` from its latest GitHub release asset.

    Returns a result dict describing what was installed:
        ``{slug, version, install_path, asset_filename, asset_url,
           sha256, digest_verified}``.
    ``digest_verified`` is False when the asset had no digest to check
    against (pre-June-2025 asset) — the download still completed, but its
    integrity was not cryptographically confirmed.

    Raises:
        ValueError: If the entry is misconfigured (wrong install_type, missing
            asset_pattern or source_url).
        RuntimeError: On any API, matching, download, digest, or extraction
            failure.
    """
    entry = get_emulator(slug)
    if entry.get("install_type") != "github_release":
        raise ValueError(f"'{slug}' is not a github_release-type emulator.")

    asset_pattern = entry.get("asset_pattern")
    if not asset_pattern:
        raise ValueError(f"No asset_pattern configured for '{slug}'.")

    binary = entry.get("binary")
    if not binary:
        raise ValueError(f"No binary configured for '{slug}'.")

    owner, repo = _parse_owner_repo(entry.get("source_url", ""))

    release = _fetch_latest_release(owner, repo)
    version = release.get("tag_name") or release.get("name") or "unknown"
    asset = _select_asset(release, asset_pattern)
    asset_name = asset.get("name", "")
    download_url = asset.get("browser_download_url")
    if not download_url:
        raise RuntimeError(
            f"Matched asset {asset_name!r} has no browser_download_url."
        )

    target_dir = (_BASE_DIR / slug).resolve()
    try:
        target_dir.relative_to(_BASE_DIR.resolve())
    except ValueError:
        raise RuntimeError(f"Install path escapes emulators/ base: {target_dir}")

    tmp_dir = Path(tempfile.mkdtemp(prefix=f"p1up-{slug}-"))
    try:
        tmp_asset = tmp_dir / asset_name
        # (3) Download completes fully before any extraction begins.
        _download_asset(download_url, tmp_asset)

        # (4) Integrity check against the asset digest when available.
        computed_sha256 = _sha256_file(tmp_asset)
        digest_verified = _verify_digest(asset, computed_sha256)

        # (5) Extract into emulators/<slug>/ with the zip-slip guard.
        target_dir.mkdir(parents=True, exist_ok=True)
        suffix = Path(asset_name).suffix.lower()
        if suffix == ".zip":
            _safe_extract_zip(tmp_asset, target_dir)
        elif suffix == ".7z":
            _safe_extract_7z(tmp_asset, target_dir)
        else:
            raise RuntimeError(
                f"Unsupported archive format {suffix!r} for asset "
                f"{asset_name!r}."
            )
    finally:
        # (7) Clean up temp files on success or failure.
        shutil.rmtree(tmp_dir, ignore_errors=True)

    binary_path = target_dir / binary
    if not binary_path.exists():
        landed = sorted(p.relative_to(target_dir).as_posix() for p in target_dir.rglob("*"))
        raise RuntimeError(
            f"Expected binary {binary!r} not found in {target_dir} after extracting "
            f"{asset_name!r}. Contents of {target_dir}: {landed}"
        )

    # (6) Ensure the portable sentinel exists post-extraction.
    ensure_portable_mode(slug, binary_path)

    # (8) Record the install.
    _record_install(
        slug=slug,
        version=version,
        install_path=str(binary_path),
        asset_filename=asset_name,
        asset_url=download_url,
        sha256_digest=computed_sha256,
        digest_verified=digest_verified,
    )

    return {
        "slug": slug,
        "version": version,
        "install_path": str(binary_path),
        "asset_filename": asset_name,
        "asset_url": download_url,
        "sha256": computed_sha256,
        "digest_verified": digest_verified,
    }
