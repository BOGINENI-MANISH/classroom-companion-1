"""
Shared pytest fixtures for all tests.
Uses an in-memory SQLite DB so tests are fully isolated.
"""
import asyncio
from datetime import datetime, timedelta
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from database.models import Base, User, Assignment, TeacherStudentLink

# ── Event loop (single-loop for whole test session) ────────────────────────────
@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


# ── In-memory async SQLite engine ─────────────────────────────────────────────
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

@pytest_asyncio.fixture(scope="session")
async def engine():
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def db(engine) -> AsyncGenerator[AsyncSession, None]:
    """Provide a fresh session, rolled back after each test."""
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        await session.begin_nested()   # savepoint
        yield session
        await session.rollback()


# ── Mock LLM provider ──────────────────────────────────────────────────────────
@pytest.fixture
def mock_llm():
    """A mock LLMProvider that returns predictable JSON/text responses."""
    llm = MagicMock()
    llm.complete         = AsyncMock()
    llm.complete_with_history = AsyncMock()
    llm.extract_text     = MagicMock(return_value='{"intent":"progress_update","confidence":0.95,"reasoning":"test"}')
    llm.extract_tool_call = MagicMock(return_value=None)
    return llm


# ── Seed helpers ───────────────────────────────────────────────────────────────
@pytest_asyncio.fixture
async def teacher_user(db: AsyncSession) -> User:
    teacher = User(
        telegram_id=100001,
        full_name="Test Teacher",
        telegram_handle="testteacher",
        role="teacher",
        invite_code="TESTTEACH",
        is_active=True,
    )
    db.add(teacher)
    await db.flush()
    return teacher


@pytest_asyncio.fixture
async def student_user(db: AsyncSession, teacher_user: User) -> User:
    student = User(
        telegram_id=200001,
        full_name="Test Student",
        telegram_handle="teststudent",
        role="student",
        is_active=True,
    )
    db.add(student)
    await db.flush()

    link = TeacherStudentLink(teacher_id=teacher_user.id, student_id=student.id)
    db.add(link)
    await db.flush()
    return student


@pytest_asyncio.fixture
async def active_assignment(db: AsyncSession, teacher_user: User, student_user: User) -> Assignment:
    assignment = Assignment(
        title="Test Essay",
        description="Write a 500-word essay.",
        raw_instruction="Assign Test Student a 500-word essay due in 5 days",
        teacher_id=teacher_user.id,
        student_id=student_user.id,
        due_date=datetime.utcnow() + timedelta(days=5),
        status="in_progress",
    )
    db.add(assignment)
    await db.flush()
    return assignment
