"""Install a portable emulator from the peach1up_emulator_bundles repo.

Sibling to ``emulator_installer.py``. Given an emulator slug whose catalog
entry declares ``install_type = "github_release"``, this module:

  1. Fetches ``manifest.json`` from the bundles repo's ``main`` branch, the
     single source of truth for each emulator's current bundle.
  2. Looks up the manifest entry for ``slug`` and constructs the release
     asset's download URL directly from its ``tag`` and ``asset`` fields.
  3. Downloads the asset to a temporary location, fully, before any
     extraction begins.
  4. Computes the SHA256 of the download and compares it against the
     manifest entry's ``sha256`` field.
  5. Extracts the archive into ``emulators/<slug>/`` with a zip-slip
     path-traversal guard.
  6. Ensures the portable sentinel file exists post-extraction.

Every step fails loud, there is no silent fallback. Temporary files are
removed on any failure. There is no GitHub API call anywhere in this flow,
the manifest and the predictable release-asset URL shape replace it.

Security-sensitive: this downloads and extracts an executable archive to disk
based on the fetched manifest. The zip-slip guard and the ``.git`` component
rejection are load-bearing; do not relax them.
"""

from __future__ import annotations

import hashlib
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path

import httpx

from backend.core.settings import get_base_path
from backend.service.utils.emulator_catalog import ensure_portable_mode, get_emulator

_BASE_DIR = get_base_path() / "emulators"
_SEVENZ_EXE = get_base_path() / "services" / "vendor" / "7z" / "7za.exe"
_BUNDLES_OWNER = "rymorrisj"
_BUNDLES_REPO = "peach_1up_emulator_bundles_win"
_MANIFEST_URL = (
    f"https://raw.githubusercontent.com/{_BUNDLES_OWNER}/{_BUNDLES_REPO}"
    "/main/manifest.json"
)
_RELEASE_DOWNLOAD_ROOT = (
    f"https://github.com/{_BUNDLES_OWNER}/{_BUNDLES_REPO}/releases/download"
)
_MANIFEST_TIMEOUT = 30.0
_DOWNLOAD_TIMEOUT = 300.0
_DOWNLOAD_CHUNK = 1024 * 1024  # 1 MiB
# RPCS3's win64_msvc build decompresses to ~143 MiB (149996575 bytes,
# confirmed by extracting the live release with 7za.exe), compressed size is
# ~35 MiB. PCSX2's Qt build is similar, ~140 MiB extracted from a ~27 MiB
# archive (config/emulators/pcsx2.toml). 500 MiB leaves headroom for growth
# while still bounding decompression-bomb archives.
_MAX_7Z_EXTRACT_SIZE = 500 * 1024 * 1024
_HTTP_HEADERS = {
    "User-Agent": "peach1up-emulator-installer",
}

# Required manifest.json shape, keyed by emulator slug:
#   {
#     "<slug>": {
#       "version": "0.0.41",
#       "tag": "v0.0.41",
#       "asset": "<slug>.zip",
#       "sha256": "<hex digest>",
#       "released_at": "2026-08-01T00:00:00Z"
#     },
#     ...
#   }
# ``released_at`` is part of the schema but is not consumed by this module.
_MANIFEST_REQUIRED_FIELDS = ("version", "tag", "asset", "sha256")


def _fetch_manifest() -> dict:
    """Fetch and parse manifest.json from the bundles repo's main branch.

    Raises:
        RuntimeError: On any non-2xx response or invalid JSON.
    """
    with httpx.Client(timeout=_MANIFEST_TIMEOUT, follow_redirects=True) as client:
        resp = client.get(_MANIFEST_URL, headers=_HTTP_HEADERS)
    if resp.status_code != 200:
        raise RuntimeError(
            f"Manifest fetch returned {resp.status_code} for {_MANIFEST_URL}: "
            f"{resp.text[:300]}"
        )
    try:
        return resp.json()
    except ValueError as exc:
        raise RuntimeError(f"Manifest at {_MANIFEST_URL} is not valid JSON: {exc}")


def _manifest_entry(manifest: dict, slug: str) -> dict:
    """Return the manifest entry for ``slug``.

    Raises:
        RuntimeError: If ``slug`` has no manifest entry, or the entry is
            missing a required field.
    """
    entry = manifest.get(slug)
    if not entry:
        raise RuntimeError(f"No manifest entry for '{slug}' at {_MANIFEST_URL}.")
    missing = [f for f in _MANIFEST_REQUIRED_FIELDS if not entry.get(f)]
    if missing:
        raise RuntimeError(
            f"Manifest entry for '{slug}' is missing required field(s): {missing}."
        )
    return entry


def _download_asset(download_url: str, dest: Path) -> None:
    """Stream ``download_url`` to ``dest``, completing fully before returning.

    Raises:
        RuntimeError: On any non-2xx response.
    """
    with httpx.Client(timeout=_DOWNLOAD_TIMEOUT, follow_redirects=True) as client:
        with client.stream("GET", download_url, headers=_HTTP_HEADERS) as resp:
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


def _verify_digest(expected_sha256: str, computed_sha256: str, asset_name: str) -> None:
    """Compare ``computed_sha256`` against the manifest's ``sha256`` field.

    Raises:
        RuntimeError: If the digests do not match.
    """
    if expected_sha256.lower() != computed_sha256.lower():
        raise RuntimeError(
            f"SHA256 mismatch for asset {asset_name!r}: "
            f"expected {expected_sha256}, computed {computed_sha256}."
        )


def _safe_extract_zip(zip_path: Path, dest_dir: Path) -> None:
    """Extract ``zip_path`` into ``dest_dir`` with a zip-slip guard.

    Each member's resolved destination is confirmed to stay within
    ``dest_dir`` before anything is written (same class of check used in the
    P-META cover-art download). Members whose path contains a ``.git``
    component are rejected, the repo's standing rule allows only the root
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


def install_from_github_release(slug: str) -> dict:
    """Download and install ``slug`` from the peach1up_emulator_bundles repo.

    Returns a result dict describing what was installed:
        ``{slug, version, install_path, asset_filename, asset_url,
           sha256, digest_verified}``.
    ``digest_verified`` is always True on a successful return, a mismatch
    raises instead of returning.

    Raises:
        ValueError: If the entry is misconfigured (wrong install_type, missing
            binary).
        RuntimeError: On any manifest, download, digest, or extraction
            failure.
    """
    entry = get_emulator(slug)
    if entry.get("install_type") != "github_release":
        raise ValueError(f"'{slug}' is not a github_release-type emulator.")

    binary = entry.get("binary")
    if not binary:
        raise ValueError(f"No binary configured for '{slug}'.")

    manifest = _fetch_manifest()
    manifest_entry = _manifest_entry(manifest, slug)
    version = manifest_entry["version"]
    asset_name = manifest_entry["asset"]
    expected_sha256 = manifest_entry["sha256"]
    download_url = f"{_RELEASE_DOWNLOAD_ROOT}/{manifest_entry['tag']}/{asset_name}"

    target_dir = (_BASE_DIR / slug).resolve()
    try:
        target_dir.relative_to(_BASE_DIR.resolve())
    except ValueError:
        raise RuntimeError(f"Install path escapes emulators/ base: {target_dir}")

    tmp_dir = Path(tempfile.mkdtemp(prefix=f"p1up-{slug}-"))
    try:
        tmp_asset = tmp_dir / asset_name
        # (2) Download completes fully before any extraction begins.
        _download_asset(download_url, tmp_asset)

        # (3) Integrity check against the manifest's expected digest.
        computed_sha256 = _sha256_file(tmp_asset)
        _verify_digest(expected_sha256, computed_sha256, asset_name)

        # (4) Extract into emulators/<slug>/ with the zip-slip guard.
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
        # Clean up temp files on success or failure.
        shutil.rmtree(tmp_dir, ignore_errors=True)

    binary_path = target_dir / binary
    if not binary_path.exists():
        landed = sorted(p.relative_to(target_dir).as_posix() for p in target_dir.rglob("*"))
        raise RuntimeError(
            f"Expected binary {binary!r} not found in {target_dir} after extracting "
            f"{asset_name!r}. Contents of {target_dir}: {landed}"
        )

    # (5) Ensure the portable sentinel exists post-extraction.
    ensure_portable_mode(slug, binary_path)

    return {
        "slug": slug,
        "version": version,
        "install_path": str(binary_path),
        "asset_filename": asset_name,
        "asset_url": download_url,
        "sha256": computed_sha256,
        "digest_verified": True,
    }
