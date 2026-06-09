import json
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from agents.base_agent import AgentResponse, BaseAgent
from database.models import Assignment, Feedback, ProgressUpdate, TeacherStudentLink, User
from llm.provider import LLMProvider
from llm.tools import tool_registry

TEACHER_SYSTEM_PROMPT = """
You are the Teacher Assistant for Classroom Companion. You help teachers assign work,
collect feedback, and stay informed about student progress.

When a teacher assigns work, extract: student name, assignment description, deadline.
When collecting feedback, transform the teacher's words into encouraging, constructive feedback
that will motivate the student.
When answering queries about students, synthesise the available information clearly and helpfully.

Always be professional, clear, and efficient. Teachers are busy — keep responses concise.
""".strip()


class TeacherAgent(BaseAgent):
    """Handles all teacher-side conversations."""

    def __init__(self, llm: LLMProvider, db: AsyncSession):
        super().__init__(llm, db)

    async def handle(self, telegram_id: int, message: str, **kwargs) -> AgentResponse:
        """Route to the appropriate method based on intent passed in kwargs."""
        intent = kwargs.get("intent", "unknown")

        if intent == "assign_work":
            return await self.handle_assignment_instruction(telegram_id, message)
        elif intent == "teacher_query":
            return await self.handle_student_query(telegram_id, message)
        elif intent == "request_summary":
            return await self.handle_summary_request(telegram_id)
        elif intent == "feedback":
            assignment_id = kwargs.get("assignment_id")
            if assignment_id:
                return await self.handle_feedback(telegram_id, assignment_id, message)
            return self._error(
                "⚠️ I couldn't find which assignment this feedback is for. "
                "Please try again after a student submits their work."
            )
        else:
            return self._error(
                "I didn't quite understand that. You can:\n"
                "• Assign work: 'Assign Riya a 500-word essay on photosynthesis, due in 3 days'\n"
                "• Ask about a student: 'How is Riya doing?'\n"
                "• Get a summary: /status"
            )

    # ── Helpers ────────────────────────────────────────────────────────────────

    async def _get_teacher(self, telegram_id: int) -> Optional[User]:
        result = await self.db.execute(
            select(User).where(User.telegram_id == telegram_id, User.role == "teacher")
        )
        return result.scalar_one_or_none()

    async def _get_linked_students(self, teacher_id: int) -> list[User]:
        result = await self.db.execute(
            select(User)
            .join(TeacherStudentLink, TeacherStudentLink.student_id == User.id)
            .where(TeacherStudentLink.teacher_id == teacher_id)
        )
        return list(result.scalars().all())

    async def _find_student_by_name(
        self, name: str, students: list[User]
    ) -> Optional[User]:
        name_lower = name.lower().strip()
        # Exact first-name or full-name match
        for s in students:
            if (
                s.full_name.lower() == name_lower
                or s.full_name.lower().split()[0] == name_lower
            ):
                return s
        # Fuzzy: name appears anywhere in full_name
        for s in students:
            if name_lower in s.full_name.lower():
                return s
        return None

    # ── Core Methods ───────────────────────────────────────────────────────────

    async def handle_assignment_instruction(
        self, teacher_telegram_id: int, message: str
    ) -> AgentResponse:
        """
        Parse the teacher's NL instruction → create Assignment → notify student.
        """
        teacher = await self._get_teacher(teacher_telegram_id)
        if not teacher:
            return self._error("❌ You are not registered as a teacher.")

        students = await self._get_linked_students(teacher.id)
        if not students:
            return self._error(
                "❌ You have no linked students yet. Share your invite code with students first."
            )

        # Step 1: parse the instruction with LLM tool
        tools = tool_registry.get_tools(["parse_assignment_instruction"])
        try:
            response = await self.llm.complete(
                system_prompt=TEACHER_SYSTEM_PROMPT,
                user_message=message,
                tools=tools,
                tool_choice={"type": "function", "function": {"name": "parse_assignment_instruction"}},
            )
            tool_result = self.llm.extract_tool_call(response)
            if not tool_result:
                return self._error("❌ I couldn't parse that assignment instruction. Please try again.")
            _, args = tool_result
        except Exception as exc:
            self.logger.error(f"LLM parse_assignment_instruction failed: {exc}")
            return self._error("❌ There was an error processing your instruction. Please try again.")

        student_name = args.get("student_name", "")
        title = args.get("title", "Assignment")
        description = args.get("description", message)
        due_days = int(args.get("due_days", 3))

        # Step 2: find student by name
        student = await self._find_student_by_name(student_name, students)
        if not student:
            student_names = ", ".join(s.full_name for s in students)
            return self._error(
                f"❌ I couldn't find a student named '{student_name}'. "
                f"Your linked students are: {student_names}"
            )

        # Step 3: create Assignment record
        due_date = datetime.utcnow() + timedelta(days=due_days)
        assignment = Assignment(
            teacher_id=teacher.id,
            student_id=student.id,
            title=title,
            description=description,
            raw_instruction=message,
            due_date=due_date,
            status="pending",
        )
        self.db.add(assignment)
        await self.db.flush()

        # Step 4: generate student-facing message
        due_date_str = due_date.strftime("%A, %d %B %Y")
        notify_msg = await self._generate_assignment_message(
            student_name=student.full_name.split()[0],
            title=title,
            description=description,
            due_date_str=due_date_str,
        )

        # Step 5: confirm to teacher
        confirm_msg = (
            f"✅ Assignment sent to {student.full_name}!\n"
            f"📚 *{title}*\n"
            f"📅 Due: {due_date_str}"
        )

        self.logger.info(
            f"Assignment created: teacher={teacher.full_name}, "
            f"student={student.full_name}, title={title}"
        )

        return self._ok(
            message=confirm_msg,
            action="notify_student",
            notify_telegram_id=student.telegram_id,
            notification_message=notify_msg,
            metadata={"assignment_id": assignment.id, "student_id": student.id},
        )

    async def _generate_assignment_message(
        self,
        student_name: str,
        title: str,
        description: str,
        due_date_str: str,
        tone: str = "warm",
    ) -> str:
        tools = tool_registry.get_tools(["generate_assignment_message"])
        user_msg = (
            f"Generate an assignment message for {student_name}. "
            f"Title: {title}. Description: {description}. Due: {due_date_str}. Tone: {tone}."
        )
        try:
            response = await self.llm.complete(
                system_prompt=TEACHER_SYSTEM_PROMPT,
                user_message=user_msg,
                tools=tools,
                tool_choice={"type": "function", "function": {"name": "generate_assignment_message"}},
            )
            tool_result = self.llm.extract_tool_call(response)
            if tool_result:
                _, args = tool_result
                return args.get("generated_message", "")
        except Exception as exc:
            self.logger.warning(f"generate_assignment_message LLM failed: {exc}")
        # Fallback
        return (
            f"📚 Hi {student_name}! You have a new assignment: *{title}*\n\n"
            f"{description}\n\n"
            f"📅 Due: {due_date_str}\n\n"
            "Good luck! Let me know if you have any questions. 💪"
        )

    async def handle_feedback(
        self, teacher_telegram_id: int, assignment_id: int, raw_feedback: str
    ) -> AgentResponse:
        """
        Format teacher feedback and send it to the student.
        Automatically determines assignment status based on feedback keywords:
        - 'redo', 'again', 'mistakes', 'fix', 'review' → status = 'in_progress'
        - 'great', 'perfect', 'ok', 'good', 'completed' → status = 'completed'
        """
        teacher = await self._get_teacher(teacher_telegram_id)
        if not teacher:
            return self._error("❌ You are not registered as a teacher.")

        # Fetch assignment with student
        result = await self.db.execute(
            select(Assignment)
            .options(selectinload(Assignment.student))
            .where(Assignment.id == assignment_id, Assignment.teacher_id == teacher.id)
        )
        assignment = result.scalar_one_or_none()
        if not assignment:
            return self._error("❌ Assignment not found.")

        student = assignment.student
        first_name = student.full_name.split()[0]

        # Step 1: format feedback via LLM
        formatted = await self._format_feedback(first_name, assignment.title, raw_feedback)

        # Step 2: analyze feedback to determine new status
        feedback_lower = raw_feedback.lower()
        new_status = "reviewed"  # default
        
        # Keywords for "do again/in progress"
        redo_keywords = ["redo", "again", "mistakes", "fix", "review", "revise", "needs work", "resubmit"]
        # Keywords for "completed/great"
        complete_keywords = ["great", "perfect", "ok", "good", "completed", "excellent", "well done", "amazing", "fantastic"]
        
        if any(kw in feedback_lower for kw in complete_keywords):
            new_status = "completed"
        elif any(kw in feedback_lower for kw in redo_keywords):
            new_status = "in_progress"

        # Step 3: persist Feedback record
        feedback = Feedback(
            assignment_id=assignment.id,
            teacher_id=teacher.id,
            raw_feedback=raw_feedback,
            formatted_feedback=formatted,
        )
        self.db.add(feedback)

        # Step 4: update assignment status
        assignment.status = new_status
        self.db.add(assignment)
        await self.db.flush()

        # Feedback message for student
        status_emoji = "✅" if new_status == "completed" else "🔄"
        student_msg = (
            f"{status_emoji} Feedback from your teacher on *{assignment.title}*:\n\n"
            f"{formatted}\n\n"
        )
        if new_status == "in_progress":
            student_msg += "📝 Please revise and resubmit your work."
        elif new_status == "completed":
            student_msg += "🎉 Great job! You've completed this assignment."

        confirm_msg = f"✅ Feedback sent to {student.full_name}!"

        self.logger.info(
            f"Feedback created: teacher={teacher.full_name}, student={student.full_name}, "
            f"status={new_status}"
        )

        return self._ok(
            message=confirm_msg,
            action="notify_student",
            notify_telegram_id=student.telegram_id,
            notification_message=student_msg,
            state_transition="idle",
            metadata={"assignment_id": assignment.id, "status": new_status},
        )

    async def _format_feedback(
        self, student_name: str, assignment_title: str, raw_feedback: str
    ) -> str:
        tools = tool_registry.get_tools(["generate_feedback_message"])
        user_msg = (
            f"Format this teacher feedback for student {student_name} "
            f"on assignment '{assignment_title}': {raw_feedback}"
        )
        try:
            response = await self.llm.complete(
                system_prompt=TEACHER_SYSTEM_PROMPT,
                user_message=user_msg,
                tools=tools,
                tool_choice={"type": "function", "function": {"name": "generate_feedback_message"}},
            )
            tool_result = self.llm.extract_tool_call(response)
            if tool_result:
                _, args = tool_result
                return args.get("formatted_message", raw_feedback)
        except Exception as exc:
            self.logger.warning(f"generate_feedback_message LLM failed: {exc}")
        return raw_feedback

    async def handle_student_query(
        self, teacher_telegram_id: int, message: str
    ) -> AgentResponse:
        """Answer teacher's question about a specific student using DB context + LLM."""
        teacher = await self._get_teacher(teacher_telegram_id)
        if not teacher:
            return self._error("❌ You are not registered as a teacher.")

        students = await self._get_linked_students(teacher.id)
        if not students:
            return self._error("You have no linked students yet.")

        # Try to find which student the teacher is asking about
        target_student: Optional[User] = None
        for student in students:
            first = student.full_name.split()[0].lower()
            if first in message.lower() or student.full_name.lower() in message.lower():
                target_student = student
                break

        if not target_student:
            # Can't identify student — ask for clarification
            names = ", ".join(s.full_name for s in students)
            return self._error(
                f"Which student are you asking about? Your students: {names}"
            )

        # Fetch all assignments + progress for this student
        result = await self.db.execute(
            select(Assignment)
            .options(
                selectinload(Assignment.progress_updates),
                selectinload(Assignment.submission),
                selectinload(Assignment.feedback),
            )
            .where(
                Assignment.teacher_id == teacher.id,
                Assignment.student_id == target_student.id,
            )
        )
        assignments = result.scalars().all()

        # Build context JSON
        context_data = []
        for a in assignments:
            context_data.append({
                "title": a.title,
                "status": a.status,
                "due_date": a.due_date.isoformat(),
                "progress_updates": [p.message for p in a.progress_updates],
                "submitted": a.submission is not None,
                "has_feedback": a.feedback is not None,
            })
        assignments_context = json.dumps(context_data, indent=2)

        tools = tool_registry.get_tools(["answer_teacher_query"])
        user_msg = (
            f"Teacher query: '{message}'\n"
            f"Student: {target_student.full_name}\n"
            f"Assignments context: {assignments_context}"
        )
        try:
            response = await self.llm.complete(
                system_prompt=TEACHER_SYSTEM_PROMPT,
                user_message=user_msg,
                tools=tools,
                tool_choice={"type": "function", "function": {"name": "answer_teacher_query"}},
            )
            tool_result = self.llm.extract_tool_call(response)
            if tool_result:
                _, args = tool_result
                answer = args.get("answer", "")
                return self._ok(answer)
        except Exception as exc:
            self.logger.error(f"answer_teacher_query LLM failed: {exc}")

        return self._error("❌ Sorry, I couldn't generate a response. Please try again.")

    async def handle_summary_request(self, teacher_telegram_id: int) -> AgentResponse:
        """Generate a full digest of all students and their assignment statuses."""
        teacher = await self._get_teacher(teacher_telegram_id)
        if not teacher:
            return self._error("❌ You are not registered as a teacher.")

        students = await self._get_linked_students(teacher.id)
        if not students:
            return self._ok(
                "📊 No students linked to your account yet. "
                "Share your invite code to get started!"
            )

        lines = [f"📊 *Class Summary for {teacher.full_name}*\n"]

        for student in students:
            result = await self.db.execute(
                select(Assignment)
                .options(selectinload(Assignment.progress_updates))
                .where(
                    Assignment.teacher_id == teacher.id,
                    Assignment.student_id == student.id,
                )
            )
            assignments = result.scalars().all()

            if not assignments:
                lines.append(f"👤 *{student.full_name}* — No assignments yet\n")
                continue

            lines.append(f"👤 *{student.full_name}*")
            for a in assignments:
                days_left = (a.due_date - datetime.utcnow()).days
                status_emoji = {
                    "pending": "📝",
                    "in_progress": "🔄",
                    "submitted": "✅",
                    "reviewed": "🌟",
                }.get(a.status, "❓")
                overdue = " ⚠️ OVERDUE" if days_left < 0 else f" ({days_left}d left)"
                lines.append(f"  {status_emoji} {a.title}{overdue}")
                if a.progress_updates:
                    latest = a.progress_updates[-1].message
                    lines.append(f"     └ Latest: {latest[:80]}")
            lines.append("")

        return self._ok("\n".join(lines))
