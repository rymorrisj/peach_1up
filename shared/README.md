# /shared

Generated directory. Do not edit manually.

- openapi.json — exported from FastAPI on startup via scripts/export_openapi.py
- types.ts — generated from openapi.json via `npm run generate:api`

To regenerate: run `python scripts/export_openapi.py` then `npm run generate:api` from the frontend directory.
