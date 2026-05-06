from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import text

from backend.core import process_registry

router = APIRouter(prefix="/api/v1", tags=["health"])


class HealthResponse(BaseModel):
    status: str
    settings_initialised: bool
    database_reachable: bool
    active_processes: int


@router.get("/health", response_model=HealthResponse)
def health_check():
    settings_ok = False
    try:
        from backend.core.settings import get_settings
        get_settings()
        settings_ok = True
    except RuntimeError:
        pass

    db_ok = False
    try:
        from backend.core.database import get_engine
        engine = get_engine()
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        db_ok = True
    except Exception:
        pass

    return HealthResponse(
        status="ok" if (settings_ok and db_ok) else "degraded",
        settings_initialised=settings_ok,
        database_reachable=db_ok,
        active_processes=process_registry.count(),
    )
