from datetime import datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from agents.base_agent import AgentResponse, BaseAgent
from database.models import Assignment, ConversationState, ProgressUpdate, Submission, TeacherStudentLink, User
from llm.provider import LLMProvider
from llm.tools import tool_registry

STUDENT_SYSTEM_PROMPT = """
You are the Student Assistant for Classroom Companion. You help students track their assignments,
report progress, and submit their work.

Be encouraging, friendly, and supportive. Students may feel stressed — your tone should be warm
and motivating. When a student reports progress, acknowledge it positively.
When they submit work, celebrate their completion enthusiastically.
""".strip()


class StudentAgent(BaseAgent):
    """Handles all student-side conversations."""

    def __init__(self, llm: LLMProvider, db: AsyncSession):
        super().__init__(llm, db)

    async def handle(self, telegram_id: int, message: str, **kwargs) -> AgentResponse:
        intent = kwargs.get("intent", "progress_update")
        file_id = kwargs.get("file_id")
        file_type = kwargs.get("file_type")
        file_name = kwargs.get("file_name")

        if intent == "submission" or file_id:
            return await self.handle_submission(
                telegram_id, message,
                file_id=file_id,
                file_type=file_type,
                file_name=file_name,
            )
        return await self.handle_progress_update(telegram_id, message)

    # ── Helpers ────────────────────────────────────────────────────────────────

    async def _get_student(self, telegram_id: int) -> Optional[User]:
        result = await self.db.execute(
            select(User).where(User.telegram_id == telegram_id, User.role == "student")
        )
        return result.scalar_one_or_none()

    async def _get_active_assignment(self, student_id: int) -> Optional[Assignment]:
        """Return the most recent non-submitted assignment for this student."""
        result = await self.db.execute(
            select(Assignment)
            .where(
                Assignment.student_id == student_id,
                Assignment.status.in_(["pending", "in_progress"]),
            )
            .order_by(Assignment.due_date.asc())
        )
        return result.scalars().first()

    async def _get_teacher_telegram_id(self, student_id: int) -> Optional[int]:
        result = await self.db.execute(
            select(User.telegram_id)
            .join(TeacherStudentLink, TeacherStudentLink.teacher_id == User.id)
            .where(TeacherStudentLink.student_id == student_id)
        )
        return result.scalar_one_or_none()

    async def _set_teacher_state(
        self, teacher_telegram_id: int, state: str, context_json: Optional[str] = None
    ) -> None:
        result = await self.db.execute(
            select(ConversationState).where(
                ConversationState.telegram_id == teacher_telegram_id
            )
        )
        cs = result.scalar_one_or_none()
        if cs:
            cs.state = state
            if context_json is not None:
                cs.context_json = context_json
            self.db.add(cs)
        else:
            self.db.add(
                ConversationState(
                    telegram_id=teacher_telegram_id,
                    state=state,
                    context_json=context_json,
                )
            )
        await self.db.flush()

    # ── Core Methods ───────────────────────────────────────────────────────────

    async def handle_progress_update(
        self, student_telegram_id: int, message: str
    ) -> AgentResponse:
        """Classify progress, store ProgressUpdate, notify teacher."""
        student = await self._get_student(student_telegram_id)
        if not student:
            return self._error("❌ You are not registered as a student.")

        assignment = await self._get_active_assignment(student.id)
        if not assignment:
            return self._ok(
                "You have no active assignments right now. "
                "Your teacher will assign something soon! 🎉"
            )

        # Step 1: classify the message
        tools = tool_registry.get_tools(["classify_student_message"])
        interpreted_status = "in_progress"
        completion_confirmed = False
        progress_description = message

        try:
            response = await self.llm.complete(
                system_prompt=STUDENT_SYSTEM_PROMPT,
                user_message=message,
                tools=tools,
                tool_choice={"type": "function", "function": {"name": "classify_student_message"}},
            )
            tool_result = self.llm.extract_tool_call(response)
            if tool_result:
                _, args = tool_result
                interpreted_status = args.get("interpreted_status", "in_progress")
                completion_confirmed = args.get("completion_confirmed", False)
                progress_description = args.get("progress_description", message)
        except Exception as exc:
            self.logger.warning(f"classify_student_message failed: {exc}")

        # If student says they're done, route to submission flow
        if completion_confirmed or interpreted_status == "completed":
            return await self.handle_submission(student_telegram_id, message)

        # Step 2: create ProgressUpdate record
        self.db.add(
            ProgressUpdate(
                assignment_id=assignment.id,
                student_id=student.id,
                message=message,
                interpreted_status=interpreted_status,
            )
        )

        # Step 3: update assignment status
        if assignment.status == "pending" and interpreted_status != "not_started":
            assignment.status = "in_progress"
            self.db.add(assignment)

        await self.db.flush()

        # Step 4: notify teacher
        teacher_tid = await self._get_teacher_telegram_id(student.id)
        teacher_msg = (
            f"📊 Progress update from *{student.full_name}*:\n"
            f"📚 Assignment: {assignment.title}\n"
            f"💬 \"{progress_description[:200]}\"\n"
            f"Status: {interpreted_status.replace('_', ' ').title()}"
        )

        # Step 5: reply to student
        encouragements = {
            "not_started": "Thanks for checking in! Get started when you can — I'm here to help 🌟",
            "in_progress": "Great progress! Keep it up, you're doing amazing! 💪",
            "nearly_done": "Almost there! You're so close — finish strong! 🚀",
        }
        reply = encouragements.get(
            interpreted_status,
            "Thanks for the update! Keep going, you've got this! 🌟"
        )

        return self._ok(
            message=reply,
            action="notify_teacher" if teacher_tid else "reply",
            notify_telegram_id=teacher_tid,
            notification_message=teacher_msg,
            metadata={"assignment_id": assignment.id, "status": interpreted_status},
        )

    async def handle_submission(
        self,
        student_telegram_id: int,
        message: str,
        file_id: Optional[str] = None,
        file_type: Optional[str] = None,
        file_name: Optional[str] = None,
        voice_transcript: Optional[str] = None,
    ) -> AgentResponse:
        """Record submission, update status, notify teacher."""
        student = await self._get_student(student_telegram_id)
        if not student:
            return self._error("❌ You are not registered as a student.")

        assignment = await self._get_active_assignment(student.id)
        if not assignment:
            # Maybe they have a submitted assignment they're trying to update
            return self._ok(
                "🎉 Looks like all your assignments are already submitted! "
                "Wait for your teacher's feedback."
            )

        # Step 1: create Submission record
        text_content = voice_transcript or (message if not file_id else None)
        submission = Submission(
            assignment_id=assignment.id,
            student_id=student.id,
            text_content=text_content,
            file_id=file_id,
            file_type=file_type,
            file_name=file_name,
            transcript=voice_transcript,
        )
        self.db.add(submission)

        # Step 2: update assignment status
        assignment.status = "submitted"
        self.db.add(assignment)
        await self.db.flush()

        # Step 3: get teacher and set their state to awaiting_feedback
        teacher_tid = await self._get_teacher_telegram_id(student.id)
        if teacher_tid:
            import json as _json
            context = _json.dumps({"assignment_id": assignment.id, "student_id": student.id})
            await self._set_teacher_state(teacher_tid, "awaiting_feedback", context)

        # Step 4: teacher notification
        file_info = ""
        if file_id and file_type:
            icons = {"photo": "🖼️", "document": "📄", "voice": "🎤"}
            icon = icons.get(file_type, "📎")
            file_info = f"\n{icon} Submitted with {file_type}"
            if file_name:
                file_info += f": {file_name}"
        elif text_content:
            preview = text_content[:200] + ("..." if len(text_content) > 200 else "")
            file_info = f"\n📝 Content: \"{preview}\""

        teacher_msg = (
            f"✅ *{student.full_name}* has submitted their work!\n"
            f"📚 Assignment: {assignment.title}{file_info}\n\n"
            f"Reply here with your feedback and I'll format and send it to them."
        )

        self.logger.info(
            f"Submission created: student={student.full_name}, assignment={assignment.title}"
        )

        return self._ok(
            message="🎉 Great work! Your submission has been sent to your teacher. "
                    "You'll receive feedback soon!",
            action="notify_teacher" if teacher_tid else "reply",
            notify_telegram_id=teacher_tid,
            notification_message=teacher_msg,
            state_transition="idle",
            metadata={"assignment_id": assignment.id, "submission_id": submission.id},
        )

    async def handle_voice_submission(
        self, student_telegram_id: int, file_id: str, duration: int
    ) -> AgentResponse:
        """Handle voice note submission — note transcript unavailable without Whisper."""
        student = await self._get_student(student_telegram_id)
        if not student:
            return self._error("❌ You are not registered as a student.")

        # Voice transcription requires Whisper API integration.
        # For now, record the file_id and note that transcript is pending.
        transcript = f"[Voice note received — {duration}s. Transcript processing not available in this version.]"

        return await self.handle_submission(
            student_telegram_id,
            message=transcript,
            file_id=file_id,
            file_type="voice",
            voice_transcript=transcript,
        )
