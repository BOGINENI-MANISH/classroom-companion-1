import json
import secrets
import string
from datetime import datetime
from typing import Optional

from loguru import logger
from sqlalchemy import select
from telegram import Update
from telegram.ext import ContextTypes

from database.database import get_async_session
from database.models import ConversationState, TeacherStudentLink, User


# ── Rate limiting ─────────────────────────────────────────────────────────────
# In-memory store: { telegram_id: [timestamp, ...] }
_rate_limit_store: dict[int, list[datetime]] = {}
RATE_LIMIT_MAX = 30      # messages
RATE_LIMIT_WINDOW = 60   # seconds


def _is_rate_limited(telegram_id: int) -> bool:
    """Return True if this user has exceeded 30 messages per 60 seconds."""
    now = datetime.utcnow()
    window_start = now.timestamp() - RATE_LIMIT_WINDOW
    history = _rate_limit_store.get(telegram_id, [])
    # Drop entries outside the window
    history = [t for t in history if t.timestamp() >= window_start]
    _rate_limit_store[telegram_id] = history
    if len(history) >= RATE_LIMIT_MAX:
        return True
    history.append(now)
    _rate_limit_store[telegram_id] = history
    return False


class BotMiddleware:
    """
    Cross-cutting concerns for every incoming Telegram update:
      1. Structured logging of every message
      2. Rate limiting (30 msg/min per user)
      3. Active-user check
      4. get_or_create_user helper
    """

    @staticmethod
    async def check(update: Update) -> Optional[str]:
        """
        Run all middleware checks. Returns an error string if the update
        should be blocked, or None if it should proceed.
        """
        if not update.effective_user:
            return "no_user"

        tid = update.effective_user.id
        text_snippet = ""
        if update.message and update.message.text:
            text_snippet = update.message.text[:60]
        elif update.message:
            text_snippet = f"[{update.message.effective_attachment.__class__.__name__}]"

        msg_type = "text"
        if update.message:
            if update.message.document:
                msg_type = "document"
            elif update.message.photo:
                msg_type = "photo"
            elif update.message.voice:
                msg_type = "voice"

        logger.info(
            f"Incoming update | tid={tid} | type={msg_type} | text='{text_snippet}'"
        )

        # Rate limit check
        if _is_rate_limited(tid):
            logger.warning(f"Rate limit exceeded for tid={tid}")
            return "rate_limited"

        # Active-user check
        async with get_async_session() as db:
            result = await db.execute(
                select(User).where(User.telegram_id == tid)
            )
            user = result.scalar_one_or_none()
            if user and not user.is_active:
                logger.warning(f"Inactive user blocked: tid={tid}")
                return "inactive"

        return None

    @staticmethod
    async def get_or_create_user(
        telegram_id: int,
        full_name: str,
        telegram_handle: Optional[str] = None,
    ) -> User:
        """
        Return the existing User or create a new one with role=None and state='idle'.
        Also ensures a ConversationState row exists.
        """
        async with get_async_session() as db:
            result = await db.execute(
                select(User).where(User.telegram_id == telegram_id)
            )
            user = result.scalar_one_or_none()

            if not user:
                user = User(
                    telegram_id=telegram_id,
                    full_name=full_name,
                    telegram_handle=telegram_handle,
                    role="unknown",
                )
                db.add(user)
                await db.flush()

                # Create initial conversation state
                db.add(ConversationState(telegram_id=telegram_id, state="idle"))
                await db.flush()

            return user


def generate_invite_code(length: int = 8) -> str:
    """Generate a random alphanumeric invite code."""
    alphabet = string.ascii_uppercase + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))
