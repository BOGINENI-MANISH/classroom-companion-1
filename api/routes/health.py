from datetime import datetime

from fastapi import APIRouter
from sqlalchemy import text

from database.database import get_async_session

router = APIRouter(tags=["health"])


@router.get("/health")
async def health_check():
    """Liveness check — also pings the database."""
    db_ok = False
    try:
        async with get_async_session() as db:
            await db.execute(text("SELECT 1"))
            db_ok = True
    except Exception:
        pass

    return {
        "status": "ok" if db_ok else "degraded",
        "database": "connected" if db_ok else "unreachable",
        "timestamp": datetime.utcnow().isoformat() + "Z",
    }
