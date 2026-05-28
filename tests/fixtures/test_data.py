"""Reusable in-memory test data factories."""
from datetime import datetime, timedelta

from database.models import Assignment, Feedback, ProgressUpdate, Reminder, Submission, User


def make_user(**kwargs) -> User:
    defaults = dict(
        telegram_id=999000,
        full_name="Sample User",
        telegram_handle="sampleuser",
        role="student",
        is_active=True,
    )
    defaults.update(kwargs)
    return User(**defaults)


def make_assignment(teacher_id: int, student_id: int, **kwargs) -> Assignment:
    defaults = dict(
        title="Sample Assignment",
        description="Do some work.",
        raw_instruction="Assign student some work due in 7 days",
        teacher_id=teacher_id,
        student_id=student_id,
        due_date=datetime.utcnow() + timedelta(days=7),
        status="pending",
    )
    defaults.update(kwargs)
    return Assignment(**defaults)


def make_progress_update(assignment_id: int, student_id: int, **kwargs) -> ProgressUpdate:
    defaults = dict(
        assignment_id=assignment_id,
        student_id=student_id,
        message="I finished the introduction.",
        interpreted_status="in_progress",
    )
    defaults.update(kwargs)
    return ProgressUpdate(**defaults)


def make_submission(assignment_id: int, student_id: int, **kwargs) -> Submission:
    defaults = dict(
        assignment_id=assignment_id,
        student_id=student_id,
        text_content="Here is my completed work.",
        file_type="text",
    )
    defaults.update(kwargs)
    return Submission(**defaults)


def make_feedback(assignment_id: int, teacher_id: int, **kwargs) -> Feedback:
    defaults = dict(
        assignment_id=assignment_id,
        teacher_id=teacher_id,
        raw_feedback="Good job!",
        formatted_feedback="Excellent work — keep it up!",
    )
    defaults.update(kwargs)
    return Feedback(**defaults)


def make_reminder(assignment_id: int, student_id: int, **kwargs) -> Reminder:
    defaults = dict(
        assignment_id=assignment_id,
        student_id=student_id,
        reminder_type="daily",
        message="Don't forget your assignment!",
        sent_at=datetime.utcnow() - timedelta(hours=10),
    )
    defaults.update(kwargs)
    return Reminder(**defaults)
