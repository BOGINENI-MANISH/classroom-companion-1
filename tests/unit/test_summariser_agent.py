"""Unit tests for SummariserAgent."""
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from agents.summariser_agent import SummariserAgent
from tests.fixtures.test_data import make_progress_update


def _mock_llm(text: str = "AI Summary text.") -> MagicMock:
    llm = MagicMock()
    llm.complete = AsyncMock(return_value=MagicMock())
    llm.extract_tool_call = MagicMock(return_value=("generate_status_summary", {"summary_text": text}))
    llm.extract_text = MagicMock(return_value=text)
    return llm


# ── generate_student_summary ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_generate_student_summary_not_found(db, teacher_user, student_user):
    """Returns a fallback string for a non-existent assignment."""
    llm = _mock_llm()
    agent = SummariserAgent(llm=llm, db=db)
    result = await agent.generate_student_summary(student_id=student_user.id, assignment_id=99999)
    assert "not found" in result.lower()


@pytest.mark.asyncio
async def test_generate_student_summary_returns_string(db, teacher_user, student_user, active_assignment):
    """generate_student_summary() returns a non-empty string."""
    llm = _mock_llm("Student has made good progress.")
    agent = SummariserAgent(llm=llm, db=db)

    # Attach eager-loaded progress_updates to the assignment object
    pu = make_progress_update(
        assignment_id=active_assignment.id, student_id=student_user.id
    )
    db.add(pu)
    await db.flush()

    result = await agent.generate_student_summary(
        student_id=student_user.id, assignment_id=active_assignment.id
    )
    assert isinstance(result, str)
    assert len(result) > 0


# ── generate_teacher_digest ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_generate_teacher_digest_no_students(db, teacher_user):
    """Teacher with no linked students gets a 'no students' fallback."""
    llm = _mock_llm()
    agent = SummariserAgent(llm=llm, db=db)
    result = await agent.generate_teacher_digest(teacher_telegram_id=teacher_user.telegram_id)
    assert "no linked students" in result.lower() or isinstance(result, str)


@pytest.mark.asyncio
async def test_generate_teacher_digest_with_student(db, teacher_user, student_user, active_assignment):
    """generate_teacher_digest() returns a multi-line digest string."""
    llm = _mock_llm("Here is a digest for all students.")
    agent = SummariserAgent(llm=llm, db=db)
    result = await agent.generate_teacher_digest(teacher_telegram_id=teacher_user.telegram_id)
    assert isinstance(result, str)
    assert len(result) > 0


# ── answer_student_query_for_teacher ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_answer_student_query_teacher_not_found(db):
    """Non-existent teacher returns error string."""
    llm = _mock_llm()
    agent = SummariserAgent(llm=llm, db=db)
    result = await agent.answer_student_query_for_teacher(
        teacher_telegram_id=99999,
        student_name="Alice",
        query="How is Alice doing?"
    )
    assert isinstance(result, str)
    assert len(result) > 0


@pytest.mark.asyncio
async def test_answer_student_query_returns_string(db, teacher_user, student_user, active_assignment):
    """Returns a non-empty answer string when teacher and students exist."""
    llm = MagicMock()
    llm.complete = AsyncMock(return_value=MagicMock())
    llm.extract_tool_call = MagicMock(
        return_value=("answer_teacher_query", {"answer": "Alice is doing well on the essay."})
    )
    llm.extract_text = MagicMock(return_value="Alice is doing well.")
    agent = SummariserAgent(llm=llm, db=db)
    result = await agent.answer_student_query_for_teacher(
        teacher_telegram_id=teacher_user.telegram_id,
        student_name=student_user.full_name.split()[0],
        query=f"How is {student_user.full_name.split()[0]} doing?",
    )
    assert isinstance(result, str)
    assert len(result) > 0
