import asyncio
from datetime import datetime, timedelta

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from database.database import get_async_session, init_db
from database.models import (
    Assignment,
    ConversationState,
    Feedback,
    ProgressUpdate,
    Reminder,
    Submission,
    TeacherStudentLink,
    User,
)


async def seed_test_data(db: AsyncSession | None = None) -> None:
    """Populate the database with realistic test data."""

    async def _seed(session: AsyncSession) -> None:
        now = datetime.utcnow()

        # ── Teachers ──────────────────────────────────────────────────────────
        teacher1 = User(
            telegram_id=100001,
            full_name="Prof. Sharma",
            role="teacher",
            invite_code="SHARMA2024",
            telegram_handle="@prof_sharma",
        )
        teacher2 = User(
            telegram_id=100002,
            full_name="Dr. Patel",
            role="teacher",
            invite_code="PATEL2024",
            telegram_handle="@dr_patel",
        )

        # ── Students ──────────────────────────────────────────────────────────
        student1 = User(
            telegram_id=200001,
            full_name="Riya Singh",
            role="student",
            telegram_handle="@riya_singh",
        )
        student2 = User(
            telegram_id=200002,
            full_name="Arjun Mehta",
            role="student",
            telegram_handle="@arjun_mehta",
        )
        student3 = User(
            telegram_id=200003,
            full_name="Priya Nair",
            role="student",
            telegram_handle="@priya_nair",
        )
        student4 = User(
            telegram_id=200004,
            full_name="Karan Gupta",
            role="student",
            telegram_handle="@karan_gupta",
        )

        session.add_all([teacher1, teacher2, student1, student2, student3, student4])
        await session.flush()

        # ── Teacher–Student Links ─────────────────────────────────────────────
        session.add_all(
            [
                TeacherStudentLink(teacher_id=teacher1.id, student_id=student1.id),
                TeacherStudentLink(teacher_id=teacher1.id, student_id=student2.id),
                TeacherStudentLink(teacher_id=teacher2.id, student_id=student3.id),
                TeacherStudentLink(teacher_id=teacher2.id, student_id=student4.id),
            ]
        )
        await session.flush()

        # ── Assignments ───────────────────────────────────────────────────────
        a1 = Assignment(
            teacher_id=teacher1.id,
            student_id=student1.id,
            title="Essay on Photosynthesis",
            description="Write a 500-word essay explaining the process of photosynthesis, "
            "including light-dependent and light-independent reactions.",
            raw_instruction="Assign Riya a 500-word essay on photosynthesis, due in 3 days",
            due_date=now + timedelta(days=3),
            status="in_progress",
        )
        a2 = Assignment(
            teacher_id=teacher1.id,
            student_id=student2.id,
            title="Quadratic Equations Practice",
            description="Solve the 10 quadratic equations provided in the worksheet. "
            "Show full working for each.",
            raw_instruction="Assign Arjun 10 quadratic equations, due in 1 day",
            due_date=now + timedelta(days=1),
            status="pending",
        )
        a3 = Assignment(
            teacher_id=teacher2.id,
            student_id=student3.id,
            title="Water Conservation Poster",
            description="Create an informative poster on water conservation techniques "
            "and the importance of saving water.",
            raw_instruction="Assign Priya to create a poster on water conservation, due in 5 days",
            due_date=now + timedelta(days=5),
            status="submitted",
        )
        a4 = Assignment(
            teacher_id=teacher2.id,
            student_id=student4.id,
            title="Book Report: Animal Farm",
            description="Write a comprehensive book report on George Orwell's Animal Farm. "
            "Include a summary, character analysis, and allegorical interpretation.",
            raw_instruction="Assign Karan a book report on Animal Farm, due yesterday",
            due_date=now - timedelta(days=1),
            status="submitted",
        )

        session.add_all([a1, a2, a3, a4])
        await session.flush()

        # ── Progress Updates ──────────────────────────────────────────────────
        session.add_all(
            [
                ProgressUpdate(
                    assignment_id=a1.id,
                    student_id=student1.id,
                    message="done 2 paragraphs, working on conclusion",
                    interpreted_status="in_progress",
                ),
                ProgressUpdate(
                    assignment_id=a3.id,
                    student_id=student3.id,
                    message="completed the poster",
                    interpreted_status="completed",
                ),
            ]
        )
        await session.flush()

        # ── Submissions ───────────────────────────────────────────────────────
        session.add_all(
            [
                Submission(
                    assignment_id=a3.id,
                    student_id=student3.id,
                    text_content="[Poster submitted via file]",
                    file_type="photo",
                    submitted_at=now - timedelta(hours=6),
                ),
                Submission(
                    assignment_id=a4.id,
                    student_id=student4.id,
                    text_content=(
                        "Here is my book report on Animal Farm. "
                        "George Orwell's Animal Farm is an allegorical novella that reflects "
                        "the events leading up to the Russian Revolution. The animals, led by "
                        "the pigs Napoleon and Snowball, overthrow the farmer Mr. Jones only to "
                        "find that the pigs gradually adopt the same oppressive behaviours. "
                        "The story teaches us that power corrupts and absolute power corrupts "
                        "absolutely."
                    ),
                    file_type=None,
                    submitted_at=now - timedelta(days=1),
                ),
            ]
        )
        await session.flush()

        # ── Feedbacks ─────────────────────────────────────────────────────────
        session.add(
            Feedback(
                assignment_id=a4.id,
                teacher_id=teacher2.id,
                raw_feedback="Good work but needs more analysis of the allegory",
                formatted_feedback=(
                    "Great effort Karan! Your report showed solid understanding. "
                    "To make it even better, try exploring the allegorical meaning behind "
                    "each character a little more deeply. Overall, really good work! 🌟"
                ),
            )
        )
        await session.flush()

        # ── Conversation States ───────────────────────────────────────────────
        for user in [teacher1, teacher2, student1, student2, student3, student4]:
            session.add(
                ConversationState(
                    telegram_id=user.telegram_id,
                    state="idle",
                )
            )
        await session.flush()

        teacher_count = 2
        student_count = 4
        assignment_count = 4
        print(
            f"✅ Seeded {teacher_count} teachers, {student_count} students, "
            f"{assignment_count} assignments"
        )

    if db is not None:
        await _seed(db)
    else:
        async with get_async_session() as session:
            await _seed(session)


async def clear_test_data(db: AsyncSession | None = None) -> None:
    """Delete all rows in reverse FK order."""

    async def _clear(session: AsyncSession) -> None:
        for model in [
            ConversationState,
            Reminder,
            Feedback,
            Submission,
            ProgressUpdate,
            Assignment,
            TeacherStudentLink,
            User,
        ]:
            await session.execute(delete(model))
        print("🗑️  All test data cleared.")

    if db is not None:
        await _clear(db)
    else:
        async with get_async_session() as session:
            await _clear(session)


async def main() -> None:
    await init_db()
    await seed_test_data()


if __name__ == "__main__":
    asyncio.run(main())
