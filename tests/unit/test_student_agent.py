"""Unit tests for StudentAgent."""
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from agents.student_agent import StudentAgent
from database.models import Assignment, ProgressUpdate, Submission
from tests.fixtures.test_data import make_assignment, make_progress_update


def _mock_llm(tool_name: str = "classify_student_message", args: dict = None) -> MagicMock:
    llm = MagicMock()
    llm.complete = AsyncMock(return_value=MagicMock())
    llm.extract_tool_call = MagicMock(return_value=(tool_name, args or {}))
    llm.extract_text = MagicMock(return_value="Great work, keep it up!")
    return llm


def _mock_llm_no_tool() -> MagicMock:
    llm = MagicMock()
    llm.complete = AsyncMock(return_value=MagicMock())
    llm.extract_tool_call = MagicMock(return_value=None)
    llm.extract_text = MagicMock(return_value="Keep going!")
    return llm


# ── handle_progress_update ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_progress_update_unregistered_student(db):
    """Returns error for telegram_id not in DB."""
    llm = _mock_llm()
    agent = StudentAgent(llm=llm, db=db)
    resp = await agent.handle_progress_update(student_telegram_id=99999, message="I'm working on it")
    assert "not registered" in resp.message.lower()


@pytest.mark.asyncio
async def test_progress_update_no_active_assignment(db, student_user):
    """Returns a gentle message when student has no active assignment."""
    # student_user exists but has no assignment in this fixture scope
    llm = _mock_llm()
    agent = StudentAgent(llm=llm, db=db)
    resp = await agent.handle_progress_update(
        student_telegram_id=student_user.telegram_id, message="I'm working on it"
    )
    assert "no active assignments" in resp.message.lower() or "assign" in resp.message.lower()


@pytest.mark.asyncio
async def test_progress_update_stores_record(db, student_user, teacher_user, active_assignment):
    """Saving a progress update creates a ProgressUpdate row."""
    from sqlalchemy import select as sa_select
    llm = _mock_llm("classify_student_message", {
        "interpreted_status": "in_progress",
        "completion_confirmed": False,
        "progress_description": "Finished intro.",
    })
    agent = StudentAgent(llm=llm, db=db)
    resp = await agent.handle_progress_update(
        student_telegram_id=student_user.telegram_id, message="Finished intro"
    )
    assert resp.action in ("reply", "notify_teacher")

    from sqlalchemy import select as sq
    result = await db.execute(
        sq(ProgressUpdate).where(ProgressUpdate.assignment_id == active_assignment.id)
    )
    updates = result.scalars().all()
    assert len(updates) >= 1


@pytest.mark.asyncio
async def test_progress_update_completion_triggers_submission_intent(db, student_user, active_assignment):
    """completion_confirmed=True should transition to submission flow."""
    llm = _mock_llm("classify_student_message", {
        "interpreted_status": "submitted",
        "completion_confirmed": True,
        "progress_description": "All done!",
    })
    agent = StudentAgent(llm=llm, db=db)
    resp = await agent.handle_progress_update(
        student_telegram_id=student_user.telegram_id, message="I'm done!"
    )
    # Should route to submission handling, confirming or updating assignment status
    assert resp.action in ("reply", "notify_teacher")


# ── handle_submission ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_submission_unregistered_student(db):
    llm = _mock_llm()
    agent = StudentAgent(llm=llm, db=db)
    resp = await agent.handle_submission(student_telegram_id=99999, message="Done!")
    assert "not registered" in resp.message.lower()


@pytest.mark.asyncio
async def test_submission_creates_submission_record(db, student_user, active_assignment):
    """handle_submission() creates a Submission row and marks assignment submitted."""
    from sqlalchemy import select as sq
    llm = _mock_llm_no_tool()
    agent = StudentAgent(llm=llm, db=db)
    llm.extract_text = MagicMock(return_value="Great, submitted!")
    resp = await agent.handle_submission(
        student_telegram_id=student_user.telegram_id,
        message="I have finished! Here it is.",
    )
    assert resp.action in ("reply", "notify_teacher")

    result = await db.execute(
        sq(Submission).where(Submission.assignment_id == active_assignment.id)
    )
    subs = result.scalars().all()
    assert len(subs) >= 1

    await db.refresh(active_assignment)
    assert active_assignment.status == "submitted"


# ── handle() router ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_handle_routes_to_submission_when_file_id(db, student_user, active_assignment):
    """Providing a file_id should route to handle_submission."""
    llm = _mock_llm_no_tool()
    agent = StudentAgent(llm=llm, db=db)
    resp = await agent.handle(
        telegram_id=student_user.telegram_id,
        message="Here's my work",
        file_id="FAKE_FILE_ID",
        file_type="document",
        file_name="essay.pdf",
    )
    assert resp.action in ("reply", "notify_teacher")


@pytest.mark.asyncio
async def test_handle_routes_to_progress_by_default(db, student_user, active_assignment):
    """Default intent should route to progress update."""
    llm = _mock_llm("classify_student_message", {
        "interpreted_status": "in_progress",
        "completion_confirmed": False,
        "progress_description": "Working on it.",
    })
    agent = StudentAgent(llm=llm, db=db)
    resp = await agent.handle(
        telegram_id=student_user.telegram_id,
        message="I'm still working on the first section.",
    )
    assert resp.action in ("reply", "notify_teacher")
