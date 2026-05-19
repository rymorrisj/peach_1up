"""Entry point for both direct invocation and PyInstaller bundle."""

from __future__ import annotations

import multiprocessing
import os
import sys

# Must be first executable line for frozen Windows builds
multiprocessing.freeze_support()

# Prevent any child re-execution from starting the server again
if multiprocessing.current_process().name != "MainProcess":
    sys.exit(0)

if __name__ == "__main__":
    if getattr(sys, "frozen", False):
        os.chdir(os.path.dirname(sys.executable))

    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w")

    import asyncio
    import uvicorn
    from backend.main import app
    from backend.core.logger import configure_uvicorn_logging

    configure_uvicorn_logging()

    config = uvicorn.Config(
        app,
        host="127.0.0.1",
        port=8000,
        log_level="info",
        loop="asyncio",
    )
    server = uvicorn.Server(config)
    asyncio.run(server.serve())
