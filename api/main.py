from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from loguru import logger

from api.routes.health import router as health_router
from api.routes.student import router as student_router
from api.routes.teacher import router as teacher_router
from config import get_settings
from database.database import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown lifecycle."""
    settings = get_settings()
    logger.info("Initialising database…")
    await init_db()
    logger.info(f"FastAPI ready — {settings.app_host}:{settings.app_port}")
    yield
    logger.info("FastAPI shutting down.")


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="Classroom Companion API",
        description="AI-powered assignment management system for teachers and students.",
        version="1.0.0",
        docs_url="/docs" if settings.debug else None,
        redoc_url="/redoc" if settings.debug else None,
        lifespan=lifespan,
    )

    # ── CORS ─────────────────────────────────────────────────────────────────
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],          # tighten in production
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Exception handlers ────────────────────────────────────────────────────
    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        logger.exception(f"Unhandled exception on {request.url}: {exc}")
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error"},
        )

    # ── Static files ──────────────────────────────────────────────────────────
    app.mount("/static", StaticFiles(directory="static"), name="static")

    # ── Routers ───────────────────────────────────────────────────────────────
    app.include_router(health_router)
    app.include_router(teacher_router)
    app.include_router(student_router)

    # ── Telegram webhook endpoint ─────────────────────────────────────────────
    # Registered separately in main.py after the bot Application is built,
    # so it is NOT wired here — this avoids a circular dependency.

    return app


# Module-level app instance used by uvicorn
app = create_app()
