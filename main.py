"""
main.py — Classroom Companion entry point.

Single-process architecture:
  FastAPI (uvicorn) + Telegram Bot (webhook/polling) + APScheduler
  all share the same asyncio event loop.

Startup sequence:
  1. Load & validate settings
  2. Configure loguru
  3. init_db() — create tables
  4. (optional) seed test data
  5. Warm up LLM provider singleton
  6. Build Telegram Application
  7. If LOCAL_DEV → start ngrok tunnel → derive WEBHOOK_BASE_URL
  8. Register Telegram webhook  -or-  fall back to polling
  9. Mount webhook route on FastAPI app
 10. Start APScheduler
 11. Start uvicorn (blocks until SIGINT/SIGTERM)

Shutdown sequence (lifespan):
  • Stop APScheduler
  • Delete Telegram webhook
  • Stop ngrok tunnel
"""

import asyncio
import sys
from contextlib import asynccontextmanager
from typing import Optional

import uvicorn
from fastapi import FastAPI, Request, Response
from loguru import logger
from telegram import Update
from telegram.ext import Application

from api.main import create_app
from bot.handlers import create_application
from config import Settings, get_settings
from database.database import init_db
from llm.provider import get_llm_provider
from scheduler.reminder_scheduler import ReminderScheduler

# ── Module-level references shared between startup & shutdown ─────────────────
_tg_application: Optional[Application] = None
_scheduler: Optional[ReminderScheduler] = None
_ngrok_tunnel = None          # pyngrok tunnel object


# ── Logging ───────────────────────────────────────────────────────────────────

def _configure_logging(settings: Settings) -> None:
    logger.remove()
    logger.add(
        sys.stderr,
        level=settings.log_level.upper(),
        format=(
            "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> — "
            "<level>{message}</level>"
        ),
        colorize=True,
    )
    logger.add(
        "logs/app.log",
        level="DEBUG",
        rotation="10 MB",
        retention="7 days",
        compression="gz",
        enqueue=True,
    )


# ── ngrok tunnel ──────────────────────────────────────────────────────────────

async def _start_ngrok(settings: Settings) -> str:
    """Start ngrok and return the public HTTPS URL."""
    try:
        from pyngrok import ngrok, conf
        from urllib.parse import urlparse

        if settings.ngrok_auth_token:
            conf.get_default().auth_token = settings.ngrok_auth_token

        # Reuse static domain when WEBHOOK_BASE_URL is already an ngrok URL
        domain: str | None = None
        if settings.webhook_base_url and "ngrok" in settings.webhook_base_url.lower():
            domain = urlparse(settings.webhook_base_url).hostname

        # Run synchronous pyngrok call in a thread executor
        loop = asyncio.get_event_loop()
        try:
            tunnel = await loop.run_in_executor(
                None,
                lambda: ngrok.connect(settings.app_port, "http", **({"domain": domain} if domain else {})),
            )
        except Exception as domain_exc:
            if domain:
                logger.warning(f"ngrok static domain '{domain}' failed ({domain_exc}), retrying with random URL…")
                tunnel = await loop.run_in_executor(
                    None,
                    lambda: ngrok.connect(settings.app_port, "http"),
                )
            else:
                raise

        public_url: str = tunnel.public_url
        if public_url.startswith("http://"):
            public_url = public_url.replace("http://", "https://", 1)

        global _ngrok_tunnel
        _ngrok_tunnel = tunnel
        logger.info(f"ngrok tunnel active: {public_url}")
        return public_url
    except Exception as exc:
        logger.error(f"ngrok failed to start: {exc}. Falling back to polling mode.")
        return ""


async def _stop_ngrok() -> None:
    global _ngrok_tunnel
    if _ngrok_tunnel is not None:
        try:
            from pyngrok import ngrok
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, lambda: ngrok.disconnect(_ngrok_tunnel.public_url))
            logger.info("ngrok tunnel disconnected.")
        except Exception as exc:
            logger.warning(f"ngrok disconnect failed: {exc}")
        _ngrok_tunnel = None


# ── Telegram webhook setup ─────────────────────────────────────────────────────

async def _register_webhook(tg_app: Application, webhook_url: str) -> bool:
    """
    Tell Telegram to POST updates to our /webhook endpoint.
    Returns True on success, False if we should fall back to polling.
    """
    try:
        await tg_app.bot.set_webhook(
            url=webhook_url,
            allowed_updates=Update.ALL_TYPES,
            drop_pending_updates=True,
        )
        info = await tg_app.bot.get_webhook_info()
        logger.info(f"Webhook registered: {info.url} (pending: {info.pending_update_count})")
        return True
    except Exception as exc:
        logger.error(f"Failed to register webhook: {exc}")
        return False


async def _delete_webhook(tg_app: Application) -> None:
    try:
        await tg_app.bot.delete_webhook(drop_pending_updates=True)
        logger.info("Telegram webhook deleted.")
    except Exception as exc:
        logger.warning(f"Failed to delete webhook: {exc}")


# ── FastAPI webhook route ─────────────────────────────────────────────────────

def _mount_webhook_route(app: FastAPI, tg_app: Application) -> None:
    """Add POST /webhook to the FastAPI app after the bot is initialised."""

    @app.post("/webhook")
    async def telegram_webhook(request: Request) -> Response:
        """Receive Telegram updates and dispatch them to python-telegram-bot."""
        try:
            data = await request.json()
            update = Update.de_json(data, tg_app.bot)
            await tg_app.process_update(update)
        except Exception as exc:
            logger.exception(f"Error processing webhook update: {exc}")
        return Response(content="ok", status_code=200)


# ── Main startup / shutdown via uvicorn lifespan ──────────────────────────────

def build_app() -> FastAPI:
    """
    Build the fully-wired FastAPI app.
    Called once at import time so uvicorn can find `app` as a module attribute.
    The heavy async startup happens inside the lifespan context manager.
    """
    settings = get_settings()
    _configure_logging(settings)

    # Create base FastAPI app (routes, CORS, static, etc.)
    app = create_app()

    # Replace the default lifespan with our extended one
    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        global _tg_application, _scheduler

        # ── Startup ───────────────────────────────────────────────────────────
        logger.info("=== Classroom Companion starting up ===")

        # 1. Database
        await init_db()
        logger.info("Database initialised.")

        # 2. Optional seed
        if settings.seed_db:
            try:
                from database.seed import seed_test_data
                from database.database import get_async_session
                async with get_async_session() as db:
                    await seed_test_data(db)
                logger.info("Test data seeded.")
            except Exception as exc:
                logger.warning(f"Seed failed (non-fatal): {exc}")

        # 3. LLM provider warm-up
        llm = get_llm_provider(settings)
        logger.info(f"LLM provider ready: {settings.llm_provider} / {settings.llm_model}")

        # 4. Build Telegram Application
        tg_app = create_application(settings)
        await tg_app.initialize()
        _tg_application = tg_app

        # 5. Determine webhook URL (ngrok or env var)
        webhook_base = settings.webhook_base_url
        using_webhook = False

        if settings.local_dev:
            tunnel_url = await _start_ngrok(settings)
            if tunnel_url:
                webhook_base = tunnel_url

        if webhook_base:
            webhook_url = webhook_base.rstrip("/") + "/webhook"
            using_webhook = await _register_webhook(tg_app, webhook_url)

        # 6. Mount webhook POST route on FastAPI
        _mount_webhook_route(_app, tg_app)

        # 7. Start bot (webhook mode doesn't need polling loop)
        await tg_app.start()
        if not using_webhook:
            logger.warning(
                "No webhook URL available — bot will NOT receive updates in this mode. "
                "Set WEBHOOK_BASE_URL or NGROK_AUTH_TOKEN to enable messaging."
            )

        # 8. Start scheduler
        sched = ReminderScheduler(tg_app.bot, settings)
        sched.start()
        _scheduler = sched

        logger.info("=== Classroom Companion ready ===")
        yield

        # ── Shutdown ──────────────────────────────────────────────────────────
        logger.info("=== Classroom Companion shutting down ===")

        if _scheduler and _scheduler.is_running:
            _scheduler.shutdown(wait=False)

        if _tg_application:
            await _delete_webhook(_tg_application)
            await _tg_application.stop()
            await _tg_application.shutdown()

        await _stop_ngrok()
        logger.info("=== Shutdown complete ===")

    # Swap in our lifespan
    app.router.lifespan_context = lifespan
    return app


# ── Module-level app for uvicorn ──────────────────────────────────────────────
app = build_app()


# ── Direct run: `python main.py` ─────────────────────────────────────────────
if __name__ == "__main__":
    settings = get_settings()

    import os
    os.makedirs("logs", exist_ok=True)

    uvicorn.run(
        "main:app",
        host=settings.app_host,
        port=settings.app_port,
        reload=False,                 # reload=True is incompatible with APScheduler
        log_level=settings.log_level.lower(),
        access_log=settings.debug,
    )
