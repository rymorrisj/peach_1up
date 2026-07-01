"""Export the FastAPI OpenAPI spec to shared/openapi.json, then generate shared/types.ts.

Builds a throwaway FastAPI instance with only the API routers — no lifespan,
no database init, no startup logic.
"""

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_PATH = REPO_ROOT / "shared" / "openapi.json"

sys.path.insert(0, str(REPO_ROOT))


def main() -> None:
    try:
        from fastapi import FastAPI
        from backend.api.routes import (
            auth, bios, emulators, filesystem, health, launches, library,
            media, platforms, profiles, settings, tags, users,
        )

        app = FastAPI(
            title="Peach 1UP",
            description="Preservation automation — REST API",
            version="0.1.0",
            docs_url="/api/docs",
            redoc_url="/api/redoc",
            openapi_url="/api/openapi.json",
            redirect_slashes=False,
        )
        app.include_router(auth.router)
        app.include_router(users.router)
        app.include_router(health.router)
        app.include_router(settings.router)
        app.include_router(emulators.router)
        app.include_router(bios.router)
        app.include_router(profiles.router)
        app.include_router(library.router)
        app.include_router(launches.router)
        app.include_router(platforms.router)
        app.include_router(filesystem.router)
        app.include_router(media.router)
        app.include_router(tags.router)

        spec = app.openapi()
        OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT_PATH.write_text(json.dumps(spec, indent=2), encoding="utf-8")
        print(f"[OK] OpenAPI spec written to {OUTPUT_PATH}")
    except Exception as exc:
        print(f"ERROR: Failed to export OpenAPI spec: {exc}", file=sys.stderr)
        sys.exit(1)

    try:
        npm = "npm.cmd" if sys.platform == "win32" else "npm"
        subprocess.run(
            [npm, "run", "generate:api"],
            cwd=REPO_ROOT / "frontend",
            check=True,
        )
        print("[OK] Types generated successfully → shared/types.ts")
    except subprocess.CalledProcessError as exc:
        print(f"ERROR: Type generation failed (exit {exc.returncode})", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
