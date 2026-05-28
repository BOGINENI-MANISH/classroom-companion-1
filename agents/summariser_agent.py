import json
from datetime import datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from agents.base_agent import AgentResponse, BaseAgent
from database.models import Assignment, TeacherStudentLink, User
from llm.provider import LLMProvider
from llm.tools import tool_registry

SUMMARISER_SYSTEM_PROMPT = """
You generate clear, actionable status reports about student assignment progress.
For teachers: summarise each student's status concisely. Flag concerns (overdue, no progress).
Use emoji sparingly to improve scannability: ✅ submitted, 🔄 in progress, ⚠️ at risk, ❌ overdue.
Keep each student summary to 2-3 lines max.
""".strip()


class SummariserAgent(BaseAgent):
    """Generates proactive and on-demand summaries for teachers."""

    def __init__(self, llm: LLMProvider, db: AsyncSession):
        super().__init__(llm, db)

    async def handle(self, telegram_id: int, message: str, **kwargs) -> AgentResponse:
        digest = await self.generate_teacher_digest(telegram_id)
        return self._ok(digest)

    async def generate_student_summary(
        self, student_id: int, assignment_id: int
    ) -> str:
        """Generate a 2-3 line summary of a single assignment for the teacher."""
        result = await self.db.execute(
            select(Assignment)
            .options(
                selectinload(Assignment.student),
                selectinload(Assignment.progress_updates),
                selectinload(Assignment.submission),
            )
            .where(Assignment.id == assignment_id, Assignment.student_id == student_id)
        )
        assignment = result.scalar_one_or_none()
        if not assignment:
            return "Assignment not found."

        student = assignment.student
        progress_msgs = [p.message for p in assignment.progress_updates]
        due_date_str = assignment.due_date.strftime("%d %b %Y")

        tools = tool_registry.get_tools(["generate_status_summary"])
        user_msg = (
            f"Summarise progress for {student.full_name} on '{assignment.title}'. "
            f"Status: {assignment.status}. Due: {due_date_str}. "
            f"Progress updates: {progress_msgs}"
        )
        try:
            response = await self.llm.complete(
                system_prompt=SUMMARISER_SYSTEM_PROMPT,
                user_message=user_msg,
                tools=tools,
                tool_choice={"type": "function", "function": {"name": "generate_status_summary"}},
            )
            tool_result = self.llm.extract_tool_call(response)
            if tool_result:
                _, args = tool_result
                return args.get("summary_text", "")
        except Exception as exc:
            self.logger.warning(f"generate_status_summary LLM failed: {exc}")

        # Fallback
        days_left = (assignment.due_date - datetime.utcnow()).days
        overdue = " (OVERDUE)" if days_left < 0 else f" ({days_left}d left)"
        return (
            f"{student.full_name} — {assignment.title}: {assignment.status}{overdue}\n"
            + (f"Latest: {progress_msgs[-1][:100]}" if progress_msgs else "No updates yet.")
        )

    async def generate_teacher_digest(self, teacher_telegram_id: int) -> str:
        """Full digest of all students and their assignments for a teacher."""
        # Get teacher
        result = await self.db.execute(
            select(User).where(
                User.telegram_id == teacher_telegram_id, User.role == "teacher"
            )
        )
        teacher = result.scalar_one_or_none()
        if not teacher:
            return "❌ Teacher not found."

        # Get linked students
        result = await self.db.execute(
            select(User)
            .join(TeacherStudentLink, TeacherStudentLink.student_id == User.id)
            .where(TeacherStudentLink.teacher_id == teacher.id)
        )
        students = result.scalars().all()

        if not students:
            return "📊 No students linked to your account yet."

        lines = [f"📊 *Weekly Digest — {teacher.full_name}*\n"]
        now = datetime.utcnow()

        for student in students:
            result = await self.db.execute(
                select(Assignment)
                .options(
                    selectinload(Assignment.progress_updates),
                    selectinload(Assignment.submission),
                    selectinload(Assignment.feedback),
                )
                .where(
                    Assignment.teacher_id == teacher.id,
                    Assignment.student_id == student.id,
                )
            )
            assignments = result.scalars().all()

            if not assignments:
                lines.append(f"👤 *{student.full_name}* — No assignments")
                continue

            lines.append(f"👤 *{student.full_name}*")
            for a in assignments:
                days_left = (a.due_date - now).days
                emoji = {
                    "pending": "📝",
                    "in_progress": "🔄",
                    "submitted": "✅",
                    "reviewed": "🌟",
                }.get(a.status, "❓")

                if days_left < 0 and a.status not in ("submitted", "reviewed"):
                    emoji = "❌"
                    timing = f"Overdue by {abs(days_left)}d"
                elif days_left <= 2 and a.status not in ("submitted", "reviewed"):
                    emoji = "⚠️"
                    timing = f"{days_left}d left — at risk"
                elif days_left < 0:
                    timing = "submitted"
                else:
                    timing = f"{days_left}d left"

                lines.append(f"  {emoji} {a.title} [{timing}]")
                if a.progress_updates:
                    latest = sorted(a.progress_updates, key=lambda p: p.created_at)[-1]
                    lines.append(f"     └ {latest.message[:80]}")
            lines.append("")

        return "\n".join(lines)

    async def answer_student_query_for_teacher(
        self, teacher_telegram_id: int, student_name: str, query: str
    ) -> str:
        """LLM-powered answer to a teacher's question about a specific student."""
        # Get teacher
        result = await self.db.execute(
            select(User).where(
                User.telegram_id == teacher_telegram_id, User.role == "teacher"
            )
        )
        teacher = result.scalar_one_or_none()
        if not teacher:
            return "❌ Teacher not found."

        # Find the student by name among linked students
        result = await self.db.execute(
            select(User)
            .join(TeacherStudentLink, TeacherStudentLink.student_id == User.id)
            .where(TeacherStudentLink.teacher_id == teacher.id)
        )
        students = result.scalars().all()
        target: Optional[User] = None
        for s in students:
            if student_name.lower() in s.full_name.lower():
                target = s
                break

        if not target:
            return f"❌ Student '{student_name}' not found in your class."

        # Gather assignment context
        result = await self.db.execute(
            select(Assignment)
            .options(
                selectinload(Assignment.progress_updates),
                selectinload(Assignment.submission),
                selectinload(Assignment.feedback),
            )
            .where(
                Assignment.teacher_id == teacher.id,
                Assignment.student_id == target.id,
            )
        )
        assignments = result.scalars().all()
        context_data = [
            {
                "title": a.title,
                "status": a.status,
                "due_date": a.due_date.isoformat(),
                "progress_updates": [p.message for p in a.progress_updates],
                "submitted": a.submission is not None,
                "has_feedback": a.feedback is not None,
            }
            for a in assignments
        ]
        assignments_context = json.dumps(context_data, indent=2)

        tools = tool_registry.get_tools(["answer_teacher_query"])
        user_msg = (
            f"Query: '{query}'\n"
            f"Student: {target.full_name}\n"
            f"Context: {assignments_context}"
        )
        try:
            response = await self.llm.complete(
                system_prompt=SUMMARISER_SYSTEM_PROMPT,
                user_message=user_msg,
                tools=tools,
                tool_choice={"type": "function", "function": {"name": "answer_teacher_query"}},
            )
            tool_result = self.llm.extract_tool_call(response)
            if tool_result:
                _, args = tool_result
                return args.get("answer", "")
        except Exception as exc:
            self.logger.error(f"answer_teacher_query LLM failed: {exc}")

        return f"Could not generate a response for query: {query}"
