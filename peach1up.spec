# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for Peach 1UP — one-dir build.
# Prerequisites: build frontend (npm run build) before running pyinstaller.

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
        ("emulators/", "emulators/"),
    ],
    hiddenimports=[
        "uvicorn",
        "uvicorn.logging",
        "uvicorn.loops",
        "uvicorn.loops.auto",
        "uvicorn.protocols",
        "uvicorn.protocols.http",
        "uvicorn.protocols.http.auto",
        "uvicorn.protocols.websockets",
        "uvicorn.protocols.websockets.auto",
        "uvicorn.lifespan",
        "uvicorn.lifespan.on",
        "uvicorn.main",
        "fastapi",
        "starlette",
        "pystray",
        "pystray._win32",
        "PIL",
        "PIL.Image",
        "sqlalchemy",
        "sqlalchemy.dialects.sqlite",
        "sqlmodel",
        "passlib",
        "passlib.handlers",
        "passlib.handlers.bcrypt",
        "passlib.handlers.argon2",
        "argon2",
        "pydantic",
        "pydantic_settings",
        "itsdangerous",
        "jose",
        "yaml",
    ],
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

# Strip __pycache__ and test files from datas
a.datas = [
    (dest, src, kind)
    for dest, src, kind in a.datas
    if "__pycache__" not in dest
    and not any(seg in dest for seg in ("test_", "_test.", "/tests/", "/test/"))
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
    console=False,
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
