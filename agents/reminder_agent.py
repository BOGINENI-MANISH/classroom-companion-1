from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from agents.base_agent import AgentResponse, BaseAgent
from database.models import Assignment, Reminder, User
from llm.provider import LLMProvider
from llm.tools import tool_registry

REMINDER_SYSTEM_PROMPT = """
You are crafting reminder messages for students about their assignments.
Be encouraging, not nagging. Vary the wording across reminders so they don't feel robotic.
For near-deadline reminders, convey urgency while staying supportive.
Personalize using the student's name and specific assignment details.
""".strip()

# Minimum gap between reminders to the same student for the same assignment (hours)
MIN_REMINDER_GAP_HOURS = 8


class ReminderAgent(BaseAgent):
    """Driven by APScheduler — determines when to send reminders and generates messages."""

    def __init__(self, llm: LLMProvider, db: AsyncSession):
        super().__init__(llm, db)

    async def handle(self, telegram_id: int, message: str, **kwargs) -> AgentResponse:
        """Not used directly — ReminderAgent is driven by the scheduler."""
        return self._ok("Reminder agent is scheduler-driven.", action="no_reply")

    async def process_due_reminders(self, bot, reminder_type: str = "daily") -> None:
        """
        Called by APScheduler. Evaluates all active assignments and sends reminders
        according to the reminder intelligence rules.

        Rules:
        1. Daily reminders at 9 AM — only if not submitted
        2. Escalation at <= 2 days remaining — twice daily (9 AM + 6 PM)
        3. Final warning when due today — sent at 8 AM
        4. Never send if a reminder was sent within the last 8 hours
        5. Skip if student is "nearly_done" on daily — send motivational nudge instead
        6. Skip submitted assignments
        7. Overdue: notify teacher once, then stop student reminders
        """
        # Fetch all non-submitted assignments with related data
        result = await self.db.execute(
            select(Assignment)
            .options(
                selectinload(Assignment.student),
                selectinload(Assignment.teacher),
                selectinload(Assignment.reminders),
                selectinload(Assignment.progress_updates),
            )
            .where(Assignment.status.in_(["pending", "in_progress"]))
        )
        assignments = result.scalars().all()

        sent_count = 0
        for assignment in assignments:
            student = assignment.student
            if not student or not student.is_active:
                continue

            # Get the latest reminder for this assignment
            last_reminder = None
            if assignment.reminders:
                last_reminder = sorted(assignment.reminders, key=lambda r: r.sent_at)[-1]

            should_send, r_type = await self._should_send_reminder(
                assignment, last_reminder, reminder_type
            )

            if not should_send:
                continue

            # Overdue: notify teacher once, skip further student reminders
            days_remaining = (assignment.due_date - datetime.utcnow()).days
            if days_remaining < 0:
                await self._send_overdue_teacher_notification(assignment, bot)
                continue

            # Determine reminder number (for wording variation)
            reminder_count = len(assignment.reminders) + 1

            # Get latest progress
            last_progress = None
            if assignment.progress_updates:
                last_progress = sorted(
                    assignment.progress_updates, key=lambda p: p.created_at
                )[-1].message

            # Generate message
            due_date_str = assignment.due_date.strftime("%A, %d %B %Y")
            message = await self._generate_reminder_message(
                student_name=student.full_name.split()[0],
                assignment_title=assignment.title,
                due_date_str=due_date_str,
                days_remaining=max(0, days_remaining),
                last_progress=last_progress,
                reminder_number=reminder_count,
            )

            # Send via bot
            try:
                await bot.send_message(
                    chat_id=student.telegram_id,
                    text=message,
                    parse_mode="Markdown",
                )
                # Log reminder in DB
                self.db.add(
                    Reminder(
                        assignment_id=assignment.id,
                        student_id=student.id,
                        reminder_type=r_type,
                        message=message,
                    )
                )
                await self.db.flush()
                sent_count += 1
                self.logger.info(
                    f"Reminder sent: student={student.full_name}, "
                    f"assignment={assignment.title}, type={r_type}"
                )
            except Exception as exc:
                self.logger.error(
                    f"Failed to send reminder to {student.full_name}: {exc}"
                )

        self.logger.info(f"Reminder job done: {sent_count} reminders sent.")

    async def _should_send_reminder(
        self,
        assignment: Assignment,
        last_reminder: Optional[Reminder],
        requested_type: str = "daily",
    ) -> tuple[bool, str]:
        """
        Determine whether a reminder should be sent, and which type.

        Returns:
            (should_send: bool, reminder_type: str)
        """
        now = datetime.utcnow()
        days_remaining = (assignment.due_date - now).days

        # Rule 6: skip submitted assignments
        if assignment.status == "submitted":
            return False, ""

        # Rule 4: don't send if a reminder was sent within the last MIN_REMINDER_GAP_HOURS
        if last_reminder:
            gap = now - last_reminder.sent_at
            if gap < timedelta(hours=MIN_REMINDER_GAP_HOURS):
                return False, ""

        # Rule 7: overdue — teacher already notified separately
        if days_remaining < 0:
            # Check if we already sent an overdue teacher notification
            overdue_reminders = [r for r in assignment.reminders if r.reminder_type == "overdue_teacher"]
            if overdue_reminders:
                return False, ""
            return True, "overdue_teacher"  # signal to caller to notify teacher

        # Rule 3: final warning — due today
        if days_remaining == 0:
            return True, "final_warning"

        # Rule 2: escalation — 2 days or fewer remaining
        if days_remaining <= 2:
            return True, "escalation"

        # Rule 5: if nearly_done on a daily, send motivational nudge instead
        if assignment.progress_updates and requested_type == "daily":
            latest_status = sorted(
                assignment.progress_updates, key=lambda p: p.created_at
            )[-1].interpreted_status
            if latest_status == "nearly_done":
                return True, "motivational_nudge"

        # Rule 1: standard daily reminder
        if requested_type in ("daily", "check"):
            return True, "daily"

        return False, ""

    async def _generate_reminder_message(
        self,
        student_name: str,
        assignment_title: str,
        due_date_str: str,
        days_remaining: int,
        last_progress: Optional[str],
        reminder_number: int,
    ) -> str:
        tools = tool_registry.get_tools(["generate_reminder_message"])
        user_msg = (
            f"Generate reminder #{reminder_number} for {student_name}. "
            f"Assignment: {assignment_title}. Due: {due_date_str}. "
            f"Days remaining: {days_remaining}. "
            f"Last progress: {last_progress or 'none yet'}."
        )
        try:
            response = await self.llm.complete(
                system_prompt=REMINDER_SYSTEM_PROMPT,
                user_message=user_msg,
                tools=tools,
                tool_choice={"type": "function", "function": {"name": "generate_reminder_message"}},
            )
            tool_result = self.llm.extract_tool_call(response)
            if tool_result:
                _, args = tool_result
                return args.get("generated_message", "")
        except Exception as exc:
            self.logger.warning(f"generate_reminder_message LLM failed: {exc}")

        # Fallback
        urgency = "⚠️ Urgent: " if days_remaining <= 1 else ""
        return (
            f"{urgency}Hi {student_name}! Just a reminder about *{assignment_title}*. "
            f"Due: {due_date_str} ({days_remaining} days left). "
            f"You've got this! 💪"
        )

    async def _send_overdue_teacher_notification(
        self, assignment: Assignment, bot
    ) -> None:
        """Notify teacher once when an assignment becomes overdue."""
        # Check if we've already notified the teacher
        overdue_sent = any(
            r.reminder_type == "overdue_teacher" for r in assignment.reminders
        )
        if overdue_sent:
            return

        teacher = assignment.teacher
        student = assignment.student
        if not teacher or not student:
            return

        days_overdue = abs((assignment.due_date - datetime.utcnow()).days)
        msg = (
            f"⚠️ *Overdue Assignment Alert*\n\n"
            f"*{student.full_name}* has not submitted *{assignment.title}*.\n"
            f"It was due {days_overdue} day(s) ago.\n\n"
            f"You may want to reach out to them directly."
        )

        try:
            await bot.send_message(
                chat_id=teacher.telegram_id,
                text=msg,
                parse_mode="Markdown",
            )
            self.db.add(
                Reminder(
                    assignment_id=assignment.id,
                    student_id=student.id,
                    reminder_type="overdue_teacher",
                    message=msg,
                )
            )
            await self.db.flush()
            self.logger.info(
                f"Overdue notification sent: teacher={teacher.full_name}, "
                f"student={student.full_name}"
            )
        except Exception as exc:
            self.logger.error(f"Failed to send overdue notification: {exc}")
