"""Unit tests for ReminderAgent._should_send_reminder().

_should_send_reminder() is pure logic — it doesn't make DB calls, only
inspects the assignment object passed to it. We use SimpleNamespace objects
to avoid SQLAlchemy ORM greenlet issues in a unit-test context.
"""
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from agents.reminder_agent import ReminderAgent, MIN_REMINDER_GAP_HOURS


# ── Helpers ───────────────────────────────────────────────────────────────────

def _agent(db) -> ReminderAgent:
    llm = MagicMock()
    llm.complete = AsyncMock(return_value=MagicMock())
    llm.extract_text = MagicMock(return_value="Great reminder message!")
    llm.extract_tool_call = MagicMock(return_value=None)
    return ReminderAgent(llm=llm, db=db)


def _assignment(
    status: str = "in_progress",
    days_from_now: float = 5,
    reminders=None,
    progress_updates=None,
) -> SimpleNamespace:
    return SimpleNamespace(
        status=status,
        due_date=datetime.utcnow() + timedelta(days=days_from_now),
        reminders=[] if reminders is None else reminders,
        progress_updates=[] if progress_updates is None else progress_updates,
    )


def _reminder(reminder_type: str, hours_ago: float) -> SimpleNamespace:
    return SimpleNamespace(
        reminder_type=reminder_type,
        sent_at=datetime.utcnow() - timedelta(hours=hours_ago),
    )


def _progress(interpreted_status: str) -> SimpleNamespace:
    return SimpleNamespace(
        interpreted_status=interpreted_status,
        created_at=datetime.utcnow(),
    )


# ── Tests ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_skip_submitted_assignment(db):
    """Submitted assignments never get reminders (Rule 6)."""
    a = _assignment(status="submitted")
    agent = _agent(db)
    should_send, _ = await agent._should_send_reminder(a, None, "daily")
    assert should_send is False


@pytest.mark.asyncio
async def test_skip_within_gap(db):
    """No reminder if last one was within MIN_REMINDER_GAP_HOURS (Rule 4)."""
    recent = _reminder("daily", hours_ago=MIN_REMINDER_GAP_HOURS - 1)
    a = _assignment()
    agent = _agent(db)
    should_send, _ = await agent._should_send_reminder(a, recent, "daily")
    assert should_send is False


@pytest.mark.asyncio
async def test_send_after_gap(db):
    """Daily reminder fires when last reminder was > gap ago (Rule 1)."""
    old = _reminder("daily", hours_ago=MIN_REMINDER_GAP_HOURS + 2)
    a = _assignment()
    agent = _agent(db)
    should_send, r_type = await agent._should_send_reminder(a, old, "daily")
    assert should_send is True
    assert r_type == "daily"


@pytest.mark.asyncio
async def test_no_previous_reminder(db):
    """Daily reminder fires when there is no previous reminder at all."""
    a = _assignment()
    agent = _agent(db)
    should_send, r_type = await agent._should_send_reminder(a, None, "daily")
    assert should_send is True
    assert r_type == "daily"


@pytest.mark.asyncio
async def test_escalation_two_days_left(db):
    """<= 2 days remaining → escalation type (Rule 2)."""
    a = _assignment(days_from_now=2)
    agent = _agent(db)
    should_send, r_type = await agent._should_send_reminder(a, None, "escalation")
    assert should_send is True
    assert r_type == "escalation"


@pytest.mark.asyncio
async def test_final_warning_due_today(db):
    """0 days remaining → final_warning type (Rule 3)."""
    # Use 0.5 days (12 h) so due_date is ahead of now but days_remaining == 0
    a = _assignment(days_from_now=0.5)
    agent = _agent(db)
    should_send, r_type = await agent._should_send_reminder(a, None, "final_warning")
    assert should_send is True
    assert r_type == "final_warning"


@pytest.mark.asyncio
async def test_overdue_triggers_teacher_notification(db):
    """Overdue with no prior teacher notice → overdue_teacher (Rule 7)."""
    a = _assignment(days_from_now=-2)
    agent = _agent(db)
    should_send, r_type = await agent._should_send_reminder(a, None, "daily")
    assert should_send is True
    assert r_type == "overdue_teacher"


@pytest.mark.asyncio
async def test_overdue_skip_if_already_notified(db):
    """If overdue_teacher reminder already sent, do not repeat it (Rule 7)."""
    overdue_r = _reminder("overdue_teacher", hours_ago=24)
    a = _assignment(days_from_now=-2, reminders=[overdue_r])
    agent = _agent(db)
    should_send, _ = await agent._should_send_reminder(a, overdue_r, "daily")
    assert should_send is False


@pytest.mark.asyncio
async def test_nearly_done_becomes_motivational_nudge(db):
    """Latest progress 'nearly_done' on daily → motivational_nudge (Rule 5)."""
    pu = _progress("nearly_done")
    a = _assignment(days_from_now=6, progress_updates=[pu])
    agent = _agent(db)
    should_send, r_type = await agent._should_send_reminder(a, None, "daily")
    assert should_send is True
    assert r_type == "motivational_nudge"


@pytest.mark.asyncio
async def test_not_nearly_done_stays_daily(db):
    """Progress status other than 'nearly_done' still gets daily reminder."""
    pu = _progress("in_progress")
    a = _assignment(days_from_now=6, progress_updates=[pu])
    agent = _agent(db)
    should_send, r_type = await agent._should_send_reminder(a, None, "daily")
    assert should_send is True
    assert r_type == "daily"
