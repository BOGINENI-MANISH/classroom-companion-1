from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agents.summariser_agent import SummariserAgent
from agents.teacher_agent import TeacherAgent
from database.database import get_db
from database.models import Assignment, ProgressUpdate, Submission, User, Feedback
from llm.provider import get_llm_provider

router = APIRouter(prefix="/api/teacher", tags=["teacher"])


# ── Pydantic schemas ──────────────────────────────────────────────────────────

class StudentInfo(BaseModel):
    id: int
    telegram_id: int
    full_name: str
    telegram_handle: Optional[str] = None

    class Config:
        from_attributes = True


class AssignmentOut(BaseModel):
    id: int
    title: str
    description: Optional[str] = None
    due_date: datetime
    status: str
    created_at: datetime
    student_id: int
    student_name: Optional[str] = None

    class Config:
        from_attributes = True


class AssignmentCreateIn(BaseModel):
    student_telegram_id: int
    title: str
    description: str
    due_date: datetime


class DashboardOut(BaseModel):
    teacher: StudentInfo
    total_students: int
    assignments_pending: int
    assignments_submitted: int
    assignments_reviewed: int
    assignments_in_progress: int


# ── Helper ────────────────────────────────────────────────────────────────────

async def _get_teacher_or_404(teacher_id: int, db: AsyncSession) -> User:
    result = await db.execute(
        select(User).where(User.id == teacher_id, User.role == "teacher")
    )
    teacher = result.scalar_one_or_none()
    if not teacher:
        raise HTTPException(status_code=404, detail="Teacher not found")
    return teacher


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("/{teacher_id}/dashboard", response_model=DashboardOut)
async def teacher_dashboard(
    teacher_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Summary counts for the teacher dashboard landing page."""
    teacher = await _get_teacher_or_404(teacher_id, db)

    from database.models import TeacherStudentLink
    links = await db.execute(
        select(TeacherStudentLink).where(TeacherStudentLink.teacher_id == teacher.id)
    )
    student_ids = [lnk.student_id for lnk in links.scalars().all()]

    assignments = await db.execute(
        select(Assignment).where(Assignment.teacher_id == teacher.id)
    )
    all_assignments = assignments.scalars().all()

    counts = {"pending": 0, "in_progress": 0, "submitted": 0, "reviewed": 0}
    for a in all_assignments:
        if a.status in counts:
            counts[a.status] += 1

    return DashboardOut(
        teacher=StudentInfo(
            id=teacher.id,
            telegram_id=teacher.telegram_id,
            full_name=teacher.full_name,
            telegram_handle=teacher.telegram_handle,
        ),
        total_students=len(student_ids),
        assignments_pending=counts["pending"],
        assignments_submitted=counts["submitted"],
        assignments_reviewed=counts["reviewed"],
        assignments_in_progress=counts["in_progress"],
    )


@router.get("/{teacher_id}/assignments", response_model=List[AssignmentOut])
async def list_teacher_assignments(
    teacher_id: int,
    status: Optional[str] = Query(None, description="Filter by status"),
    student_id: Optional[int] = Query(None, description="Filter by student DB id"),
    db: AsyncSession = Depends(get_db),
):
    """List all assignments for a teacher with optional filters."""
    await _get_teacher_or_404(teacher_id, db)

    query = select(Assignment).where(Assignment.teacher_id == teacher_id)
    if status:
        query = query.where(Assignment.status == status)
    if student_id:
        query = query.where(Assignment.student_id == student_id)
    query = query.order_by(Assignment.due_date.asc())

    result = await db.execute(query)
    assignments = result.scalars().all()

    # Attach student names
    output = []
    for a in assignments:
        student_res = await db.execute(select(User).where(User.id == a.student_id))
        student = student_res.scalar_one_or_none()
        output.append(
            AssignmentOut(
                id=a.id,
                title=a.title,
                description=a.description,
                due_date=a.due_date,
                status=a.status,
                created_at=a.created_at,
                student_id=a.student_id,
                student_name=student.full_name if student else None,
            )
        )
    return output


@router.get("/{teacher_id}/student/{student_id}/summary")
async def student_summary(
    teacher_id: int,
    student_id: int,
    db: AsyncSession = Depends(get_db),
):
    """AI-generated summary of a student's progress for the teacher UI."""
    await _get_teacher_or_404(teacher_id, db)

    result = await db.execute(select(User).where(User.id == student_id, User.role == "student"))
    student = result.scalar_one_or_none()
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")

    # Fetch assignments with latest progress
    assignments_res = await db.execute(
        select(Assignment).where(
            Assignment.teacher_id == teacher_id,
            Assignment.student_id == student_id,
        ).order_by(Assignment.due_date.asc())
    )
    assignments = assignments_res.scalars().all()

    summary_items = []
    llm = get_llm_provider()
    agent = SummariserAgent(llm, db)

    for a in assignments:
        item = await agent.generate_student_summary(student_id, a.id)
        summary_items.append({"assignment_id": a.id, "title": a.title, "summary": item})

    return {
        "student_id": student.id,
        "student_name": student.full_name,
        "assignments": summary_items,
    }


@router.post("/{teacher_id}/assignment", response_model=AssignmentOut, status_code=201)
async def create_assignment(
    teacher_id: int,
    payload: AssignmentCreateIn,
    db: AsyncSession = Depends(get_db),
):
    """
    Create an assignment directly via the REST API (used by the web UI).
    The teacher provides the student's telegram_id, title, description, and due_date.
    """
    teacher = await _get_teacher_or_404(teacher_id, db)

    # Resolve student
    student_res = await db.execute(
        select(User).where(User.telegram_id == payload.student_telegram_id, User.role == "student")
    )
    student = student_res.scalar_one_or_none()
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")

    # Verify teacher-student link
    from database.models import TeacherStudentLink
    link_res = await db.execute(
        select(TeacherStudentLink).where(
            TeacherStudentLink.teacher_id == teacher.id,
            TeacherStudentLink.student_id == student.id,
        )
    )
    if not link_res.scalar_one_or_none():
        raise HTTPException(status_code=403, detail="This student is not linked to you")

    new_assignment = Assignment(
        teacher_id=teacher.id,
        student_id=student.id,
        title=payload.title,
        description=payload.description,
        raw_instruction=payload.description,
        due_date=payload.due_date,
        status="pending",
    )
    db.add(new_assignment)
    await db.flush()

    return AssignmentOut(
        id=new_assignment.id,
        title=new_assignment.title,
        description=new_assignment.description,
        due_date=new_assignment.due_date,
        status=new_assignment.status,
        created_at=new_assignment.created_at,
        student_id=new_assignment.student_id,
        student_name=student.full_name,
    )
