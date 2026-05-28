"""Unit tests for TeacherAgent."""
import json
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from agents.teacher_agent import TeacherAgent
from agents.base_agent import AgentResponse
from database.models import Assignment
from tests.fixtures.test_data import make_assignment


def _mock_llm_tool(tool_name: str, args: dict) -> MagicMock:
    llm = MagicMock()
    llm.complete = AsyncMock(return_value=MagicMock())
    llm.extract_tool_call = MagicMock(return_value=(tool_name, args))
    llm.extract_text = MagicMock(return_value="Here is the AI message.")
    return llm


def _mock_llm_text(text: str) -> MagicMock:
    llm = MagicMock()
    llm.complete = AsyncMock(return_value=MagicMock())
    llm.extract_tool_call = MagicMock(return_value=None)
    llm.extract_text = MagicMock(return_value=text)
    return llm


# ── handle() routing ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_handle_unknown_intent_returns_error(db, teacher_user):
    llm = _mock_llm_text("")
    agent = TeacherAgent(llm=llm, db=db)
    resp = await agent.handle(teacher_user.telegram_id, "random message", intent="unknown")
    assert resp.action == "reply"
    assert "didn't quite understand" in resp.message.lower() or "didn't" in resp.message


@pytest.mark.asyncio
async def test_handle_feedback_without_assignment_id(db, teacher_user):
    llm = _mock_llm_text("")
    agent = TeacherAgent(llm=llm, db=db)
    resp = await agent.handle(teacher_user.telegram_id, "Good job!", intent="feedback")
    assert "couldn't find" in resp.message.lower() or "couldn't" in resp.message


# ── handle_assignment_instruction ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_handle_assignment_instruction_no_teacher(db):
    """Non-existent telegram_id should return an error."""
    llm = _mock_llm_tool("parse_assignment_instruction", {
        "student_name": "Alice", "title": "Essay", "description": "Write it.", "due_days": 3
    })
    agent = TeacherAgent(llm=llm, db=db)
    resp = await agent.handle_assignment_instruction(teacher_telegram_id=99999, message="Assign Alice an essay")
    assert "not registered" in resp.message.lower()


@pytest.mark.asyncio
async def test_handle_assignment_instruction_no_students(db, teacher_user):
    """Teacher with no linked students should get an appropriate error."""
    llm = _mock_llm_tool("parse_assignment_instruction", {
        "student_name": "Alice", "title": "Essay", "description": "Write it.", "due_days": 3
    })
    agent = TeacherAgent(llm=llm, db=db)
    resp = await agent.handle_assignment_instruction(
        teacher_telegram_id=teacher_user.telegram_id, message="Assign Alice an essay"
    )
    assert "no linked students" in resp.message.lower()


@pytest.mark.asyncio
async def test_handle_assignment_instruction_student_not_found(db, teacher_user, student_user):
    """Unknown student name should return an error listing available students."""
    llm = _mock_llm_tool("parse_assignment_instruction", {
        "student_name": "Nonexistent", "title": "Essay", "description": "Write it.", "due_days": 3
    })
    agent = TeacherAgent(llm=llm, db=db)
    resp = await agent.handle_assignment_instruction(
        teacher_telegram_id=teacher_user.telegram_id, message="Assign Nonexistent an essay"
    )
    assert "couldn't find" in resp.message.lower()
    assert student_user.full_name in resp.message


@pytest.mark.asyncio
async def test_handle_assignment_instruction_success(db, teacher_user, student_user):
    """Successful assignment creation notifies student and confirms to teacher."""
    llm = _mock_llm_tool("parse_assignment_instruction", {
        "student_name": student_user.full_name.split()[0],
        "title": "Test Essay",
        "description": "Write a 500-word essay.",
        "due_days": 5,
    })
    # second call (generate_assignment_message) returns text
    llm.extract_text = MagicMock(return_value="Hey! You have a new assignment.")
    agent = TeacherAgent(llm=llm, db=db)
    resp = await agent.handle_assignment_instruction(
        teacher_telegram_id=teacher_user.telegram_id,
        message=f"Assign {student_user.full_name.split()[0]} a 500-word essay due in 5 days",
    )
    assert resp.action == "notify_student"
    assert resp.notify_telegram_id == student_user.telegram_id
    assert "Test Essay" in resp.message or "sent" in resp.message.lower()


# ── _find_student_by_name ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_find_student_exact_match(db, teacher_user, student_user):
    from database.models import User
    llm = _mock_llm_text("")
    agent = TeacherAgent(llm=llm, db=db)
    students = [student_user]
    found = await agent._find_student_by_name(student_user.full_name, students)
    assert found is not None
    assert found.id == student_user.id


@pytest.mark.asyncio
async def test_find_student_first_name_match(db, student_user):
    llm = _mock_llm_text("")
    agent = TeacherAgent(llm=llm, db=db)
    first_name = student_user.full_name.split()[0]
    found = await agent._find_student_by_name(first_name, [student_user])
    assert found is not None
    assert found.id == student_user.id


@pytest.mark.asyncio
async def test_find_student_no_match(db, student_user):
    llm = _mock_llm_text("")
    agent = TeacherAgent(llm=llm, db=db)
    found = await agent._find_student_by_name("Completely Unknown Name", [student_user])
    assert found is None
