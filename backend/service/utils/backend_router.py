"""Backend routing utilities for Peach 1UP.

Maps slugs to their corresponding backend launch modules. Dispatch is
data-driven: a single dict keyed by BackendSlug.value → module path.
No if/elif chain, no frozensets, no ORM objects.
"""

from __future__ import annotations

import importlib
from typing import TYPE_CHECKING

from backend.constants_generated import BackendSlug, Era

if TYPE_CHECKING:
    from backend.service.launch.launch_spec import LaunchSpec


# Slug → importable module path. Backends that share a module (console
# emulators) all point to the same module; dispatch uses spec.slug to
# select the right ConsoleBackend inside that module.
_BACKEND_MODULES: dict[str, str] = {
    BackendSlug.DOSBOX_X.value:    "backend.service.backends.dosbox",
    BackendSlug.BOX86.value:       "backend.service.backends.box86",
    BackendSlug.XEMU.value:        "backend.service.backends.xemu",
    BackendSlug.RPCS3.value:       "backend.service.backends.rpcs3",
    BackendSlug.FLYCAST.value:     "backend.service.backends.flycast",
    BackendSlug.DUCKSTATION.value: "backend.service.backends.console",
    BackendSlug.PCSX2.value:       "backend.service.backends.console",
    BackendSlug.MESEN.value:       "backend.service.backends.console",
    BackendSlug.PROJECT64.value:   "backend.service.backends.console",
    BackendSlug.XENIA.value:       "backend.service.backends.xenia",
}


def resolve_backend_name(era: Era) -> str:
    """Resolve the backend name string for an era.

    86Box eras (win95, win98, winxp) always route to 86Box. DOS
    and console eras use the flat 'backend' key from eras.yaml.

    Args:
        era: The gaming era to resolve.

    Returns:
        A ``BackendSlug`` value string — one of the values in ``BackendSlug``.

    Raises:
        RuntimeError: If eras.yaml cannot be loaded or the era is not configured.
        ValueError: If the era has no resolvable backend.
    """
    from backend.service.utils.emulator_catalog import get_backend_for_era as _get_backend_for_era
    try:
        return _get_backend_for_era(era.value)
    except ValueError:
        pass

    # win95/win98/winxp have no flat 'backend' key — they always route to 86Box.
    if era.value in ('win95', 'win98', 'winxp'):
        return BackendSlug.BOX86.value

    raise ValueError(f"Cannot resolve backend for era '{era.value}'")


def dispatch(spec: "LaunchSpec") -> tuple:
    """Import the backend module for spec.slug and call its launch(spec).

    Args:
        spec: Fully resolved LaunchSpec. slug must match a BackendSlug value.

    Returns:
        ``(process, job_object)`` tuple from the backend launch call.

    Raises:
        ValueError: If spec.slug is not a known backend slug.
        ImportError: If the backend module cannot be imported (surfaced clearly,
            not swallowed).
        Any exception raised by the backend launch function.
    """
    module_path = _BACKEND_MODULES.get(spec.slug)
    if module_path is None:
        raise ValueError(
            f"Unknown backend slug: {spec.slug!r}. "
            f"Valid slugs: {', '.join(sorted(_BACKEND_MODULES))}"
        )
    try:
        module = importlib.import_module(module_path)
    except ImportError as exc:
        raise ImportError(
            f"Backend module '{module_path}' could not be imported: {exc}"
        ) from exc
    return module.launch(spec)


def get_executable_path(era: Era, backend_name: str | None = None) -> str:
    """Return the emulator executable path for the given era.

    Args:
        era: The gaming era to look up.
        backend_name: Already-resolved backend slug (from ``resolve_backend_name``),
            if the caller has one. When omitted, it is resolved from ``era``.

    Returns:
        Absolute path string, or empty string if the emulator is not installed.

    Raises:
        RuntimeError: If the era cannot be resolved or has no catalog entry.
    """
    from backend.service.utils.emulator_catalog import get_install_path
    if backend_name is None:
        backend_name = resolve_backend_name(era)
    catalog_slug = backend_name
    try:
        path = get_install_path(catalog_slug)
    except ValueError:
        raise RuntimeError(
            f"No executable mapping for backend '{backend_name}' (era '{era.value}'). "
            "Ensure the emulator is registered in config/emulators/."
        )
    return str(path) if path and path.is_file() else ""
