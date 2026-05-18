# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for Peach 1UP — one-dir build.
# Prerequisites: build frontend (npm run build) before running pyinstaller.

import subprocess
import sys as _sys

_merge = subprocess.run(
    [_sys.executable, "scripts/merge_emulators.py"],
    capture_output=True,
    text=True,
)
if _merge.returncode != 0:
    raise SystemExit(
        f"merge_emulators.py failed (exit {_merge.returncode}):\n{_merge.stderr}"
    )
print(_merge.stdout, end="")

from PyInstaller.utils.hooks import collect_submodules

hiddenimports = (
    collect_submodules("fastapi")
    + collect_submodules("starlette")
    + collect_submodules("uvicorn")
    + collect_submodules("sqlmodel")
    + collect_submodules("pydantic")
    + [
        "pystray",
        "pystray._win32",
        "PIL",
        "PIL.Image",
        "sqlalchemy",
        "sqlalchemy.dialects.sqlite",
        "passlib",
        "passlib.handlers",
        "passlib.handlers.bcrypt",
        "passlib.handlers.argon2",
        "argon2",
        "pydantic_settings",
        "itsdangerous",
        "jose",
        "yaml",
        "pycdlib",
    ]
)

block_cipher = None

a = Analysis(
    ["peach1up_launcher.py"],
    pathex=["."],
    binaries=[],
    datas=[
        ("backend/", "backend/"),
        ("config/", "config/"),
        ("assets/", "assets/"),
        ("frontend/dist/", "frontend/dist/"),
        ("scripts/", "scripts/"),
        ("emulators/", "emulators/"),
    ],
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "test",
        "tests",
        "testing",
        "pytest",
        "setuptools",
        "distutils",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

a.datas = [
    (dest, src, kind)
    for dest, src, kind in a.datas
    if "__pycache__" not in dest
    and not any(seg in dest for seg in ("test_", "_test.", "/tests/", "/test/"))
    and not any(part in dest for part in ("roms", "bios", "saves"))
    and dest.replace("\\", "/") != "config/emulators.yaml"
    and not dest.replace("\\", "/").startswith("config/emulators/")
]

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="peach1up",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon="assets/peach1up.png",
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="peach1up",
)