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


def _check_router_parity(export_app) -> None:
    """Fail loud if backend.main.app mounts an API route this export app lacks.

    export_app is built only from ROUTERS; backend.main.app is the real app.
    Importing backend.main only runs module-level code (routers, middleware),
    not the lifespan startup logic, so this is safe without a DB/runtime.
    """
    from fastapi.routing import APIRoute

    import backend.main as main_module

    def route_keys(app) -> set[tuple[str, str]]:
        # include_in_schema=False routes (e.g. main.py's static /media file
        # serving and the SPA catch-all) are deliberately outside the API
        # spec and aren't router modules — exclude them from the comparison.
        keys = set()
        for route in app.routes:
            if isinstance(route, APIRoute) and route.include_in_schema:
                for method in route.methods:
                    keys.add((method, route.path))
        return keys

    main_routes = route_keys(main_module.app)
    export_routes = route_keys(export_app)
    missing = main_routes - export_routes
    if missing:
        formatted = ", ".join(f"{m} {p}" for m, p in sorted(missing))
        raise RuntimeError(
            "Router parity check failed: backend.main.app mounts routes not present "
            f"in ROUTERS (backend/api/routes/__init__.py): {formatted}"
        )


def main() -> None:
    try:
        from fastapi import FastAPI
        from backend.api.routes import ROUTERS

        app = FastAPI(
            title="Peach 1UP",
            description="Preservation automation — REST API",
            version="0.1.0",
            docs_url="/api/docs",
            redoc_url="/api/redoc",
            openapi_url="/api/openapi.json",
            redirect_slashes=False,
        )
        for _router in ROUTERS:
            app.include_router(_router)

        _check_router_parity(app)

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
