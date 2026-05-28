from datetime import datetime

from fastapi import APIRouter, HTTPException
from sqlalchemy import select, text

from database.database import get_async_session
from database.models import User

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


@router.get("/api/user/by-telegram/{telegram_id}")
async def lookup_by_telegram(telegram_id: int):
    """Resolve a Telegram user ID to a DB record (id, role, full_name)."""
    async with get_async_session() as db:
        result = await db.execute(
            select(User).where(User.telegram_id == telegram_id)
        )
        user = result.scalar_one_or_none()
    if not user or user.role == "unknown":
        raise HTTPException(status_code=404, detail="User not found. Make sure you have started the bot with /start first.")
    return {"id": user.id, "role": user.role, "full_name": user.full_name}
