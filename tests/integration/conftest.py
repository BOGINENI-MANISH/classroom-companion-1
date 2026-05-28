"""
Shared fixtures for integration tests.

Creates a minimal FastAPI app (no lifespan so we don't touch the real DB),
wires in all production routers, and overrides get_db with the in-memory
test session from the top-level conftest.
"""
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncSession

from api.routes.health import router as health_router
from api.routes.student import router as student_router
from api.routes.teacher import router as teacher_router
from database.database import get_db


def _build_test_app(db: AsyncSession) -> FastAPI:
    """Minimal app with all API routers and test-DB dependency override."""
    app = FastAPI()
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
    app.include_router(health_router)
    app.include_router(teacher_router)
    app.include_router(student_router)

    async def _override_get_db():
        yield db

    app.dependency_overrides[get_db] = _override_get_db
    return app


@pytest.fixture
def mock_llm():
    """LLM mock returned by get_llm_provider in routes under test."""
    llm = MagicMock()
    llm.complete = AsyncMock(return_value=MagicMock())
    llm.extract_text = MagicMock(return_value="Mock AI summary.")
    llm.extract_tool_call = MagicMock(
        return_value=("generate_status_summary", {"summary_text": "Mock AI summary."})
    )
    return llm


@pytest_asyncio.fixture
async def teacher_client(db, teacher_user):
    """httpx.AsyncClient pre-seeded with a teacher_user."""
    app = _build_test_app(db)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield client


@pytest_asyncio.fixture
async def student_client(db, teacher_user, student_user, active_assignment):
    """httpx.AsyncClient pre-seeded with teacher, student, and one assignment."""
    app = _build_test_app(db)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield client
