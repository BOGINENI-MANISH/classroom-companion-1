from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agents.summariser_agent import SummariserAgent
from database.database import get_db
from database.models import Assignment, Feedback, ProgressUpdate, Submission, User
from llm.provider import get_llm_provider

router = APIRouter(prefix="/api/student", tags=["student"])


# ── Pydantic schemas ──────────────────────────────────────────────────────────

class ProgressUpdateOut(BaseModel):
    id: int
    message: str
    interpreted_status: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class SubmissionOut(BaseModel):
    id: int
    text_content: Optional[str] = None
    file_id: Optional[str] = None
    file_type: Optional[str] = None
    file_name: Optional[str] = None
    submitted_at: datetime

    class Config:
        from_attributes = True


class FeedbackOut(BaseModel):
    id: int
    formatted_feedback: Optional[str] = None
    raw_feedback: Optional[str] = None

    class Config:
        from_attributes = True


class AssignmentDetailOut(BaseModel):
    id: int
    title: str
    description: Optional[str] = None
    due_date: datetime
    status: str
    created_at: datetime
    teacher_name: Optional[str] = None
    progress_updates: List[ProgressUpdateOut] = []
    submission: Optional[SubmissionOut] = None
    feedback: Optional[FeedbackOut] = None
    ai_summary: Optional[str] = None


class DashboardOut(BaseModel):
    student_id: int
    student_name: str
    total_assignments: int
    pending: int
    in_progress: int
    submitted: int
    reviewed: int


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _get_student_or_404(student_id: int, db: AsyncSession) -> User:
    result = await db.execute(
        select(User).where(User.id == student_id, User.role == "student")
    )
    student = result.scalar_one_or_none()
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")
    return student


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("/{student_id}/dashboard", response_model=DashboardOut)
async def student_dashboard(
    student_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Summary counts for the student dashboard landing page."""
    student = await _get_student_or_404(student_id, db)

    result = await db.execute(
        select(Assignment).where(Assignment.student_id == student.id)
    )
    assignments = result.scalars().all()

    counts = {"pending": 0, "in_progress": 0, "submitted": 0, "reviewed": 0}
    for a in assignments:
        if a.status in counts:
            counts[a.status] += 1

    return DashboardOut(
        student_id=student.id,
        student_name=student.full_name,
        total_assignments=len(assignments),
        pending=counts["pending"],
        in_progress=counts["in_progress"],
        submitted=counts["submitted"],
        reviewed=counts["reviewed"],
    )


@router.get("/{student_id}/assignments", response_model=List[AssignmentDetailOut])
async def list_student_assignments(
    student_id: int,
    db: AsyncSession = Depends(get_db),
):
    """List all assignments for a student with full details."""
    student = await _get_student_or_404(student_id, db)

    result = await db.execute(
        select(Assignment)
        .where(Assignment.student_id == student.id)
        .order_by(Assignment.due_date.asc())
    )
    assignments = result.scalars().all()

    llm = get_llm_provider()
    agent = SummariserAgent(llm, db)

    output = []
    for a in assignments:
        # Teacher name
        teacher_res = await db.execute(select(User).where(User.id == a.teacher_id))
        teacher = teacher_res.scalar_one_or_none()

        # Progress updates
        progress_res = await db.execute(
            select(ProgressUpdate)
            .where(ProgressUpdate.assignment_id == a.id)
            .order_by(ProgressUpdate.created_at.asc())
        )
        progress_updates = [
            ProgressUpdateOut(
                id=p.id,
                message=p.message,
                interpreted_status=p.interpreted_status,
                created_at=p.created_at,
            )
            for p in progress_res.scalars().all()
        ]

        # Submission
        sub_res = await db.execute(
            select(Submission).where(Submission.assignment_id == a.id)
        )
        sub = sub_res.scalar_one_or_none()
        submission_out = None
        if sub:
            submission_out = SubmissionOut(
                id=sub.id,
                text_content=sub.text_content,
                file_id=sub.file_id,
                file_type=sub.file_type,
                file_name=sub.file_name,
                submitted_at=sub.submitted_at,
            )

        # Feedback
        fb_res = await db.execute(
            select(Feedback).where(Feedback.assignment_id == a.id)
        )
        fb = fb_res.scalar_one_or_none()
        feedback_out = None
        if fb:
            feedback_out = FeedbackOut(
                id=fb.id,
                formatted_feedback=fb.formatted_feedback,
                raw_feedback=fb.raw_feedback,
            )

        # AI summary
        try:
            ai_summary = await agent.generate_student_summary(student.id, a.id)
        except Exception:
            ai_summary = None

        output.append(
            AssignmentDetailOut(
                id=a.id,
                title=a.title,
                description=a.description,
                due_date=a.due_date,
                status=a.status,
                created_at=a.created_at,
                teacher_name=teacher.full_name if teacher else None,
                progress_updates=progress_updates,
                submission=submission_out,
                feedback=feedback_out,
                ai_summary=ai_summary,
            )
        )

    return output


@router.get("/{student_id}/assignments/{assignment_id}", response_model=AssignmentDetailOut)
async def get_assignment_detail(
    student_id: int,
    assignment_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Detailed view of a single assignment for the student UI."""
    student = await _get_student_or_404(student_id, db)

    result = await db.execute(
        select(Assignment).where(
            Assignment.id == assignment_id,
            Assignment.student_id == student.id,
        )
    )
    assignment = result.scalar_one_or_none()
    if not assignment:
        raise HTTPException(status_code=404, detail="Assignment not found")

    llm = get_llm_provider()
    agent = SummariserAgent(llm, db)

    # Teacher name
    teacher_res = await db.execute(select(User).where(User.id == assignment.teacher_id))
    teacher = teacher_res.scalar_one_or_none()

    # Progress updates
    progress_res = await db.execute(
        select(ProgressUpdate)
        .where(ProgressUpdate.assignment_id == assignment.id)
        .order_by(ProgressUpdate.created_at.asc())
    )
    progress_updates = [
        ProgressUpdateOut(
            id=p.id,
            message=p.message,
            interpreted_status=p.interpreted_status,
            created_at=p.created_at,
        )
        for p in progress_res.scalars().all()
    ]

    # Submission
    sub_res = await db.execute(
        select(Submission).where(Submission.assignment_id == assignment.id)
    )
    sub = sub_res.scalar_one_or_none()
    submission_out = None
    if sub:
        submission_out = SubmissionOut(
            id=sub.id,
            text_content=sub.text_content,
            file_id=sub.file_id,
            file_type=sub.file_type,
            file_name=sub.file_name,
            submitted_at=sub.submitted_at,
        )

    # Feedback
    fb_res = await db.execute(
        select(Feedback).where(Feedback.assignment_id == assignment.id)
    )
    fb = fb_res.scalar_one_or_none()
    feedback_out = None
    if fb:
        feedback_out = FeedbackOut(
            id=fb.id,
            formatted_feedback=fb.formatted_feedback,
            raw_feedback=fb.raw_feedback,
        )

    # AI summary
    try:
        ai_summary = await agent.generate_student_summary(student.id, assignment.id)
    except Exception:
        ai_summary = None

    return AssignmentDetailOut(
        id=assignment.id,
        title=assignment.title,
        description=assignment.description,
        due_date=assignment.due_date,
        status=assignment.status,
        created_at=assignment.created_at,
        teacher_name=teacher.full_name if teacher else None,
        progress_updates=progress_updates,
        submission=submission_out,
        feedback=feedback_out,
        ai_summary=ai_summary,
    )
