"""
scheduler/reminder_scheduler.py

Manages all APScheduler jobs for the Classroom Companion bot.
All jobs share the same asyncio event loop as FastAPI and python-telegram-bot.

Jobs registered:
  1. daily_reminders      — cron: every day at 09:00 (config: reminder_daily_hour/minute)
  2. escalation_reminders — cron: every day at 18:00  (assignments due in ≤2 days)
  3. final_warning        — cron: every day at 08:00  (assignments due today)
  4. overdue_check        — interval: every 6 hours    (notify teacher of overdue work)
  5. teacher_digest       — cron: Monday at 08:00      (weekly class digest to teachers)
"""

from typing import Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from loguru import logger
from sqlalchemy import select
from telegram import Bot

from agents.reminder_agent import ReminderAgent
from agents.summariser_agent import SummariserAgent
from config import Settings, get_settings
from database.database import get_async_session
from database.models import User
from llm.provider import get_llm_provider


class ReminderScheduler:
    """Wraps APScheduler and owns all reminder/digest jobs."""

    def __init__(self, bot: Bot, settings: Optional[Settings] = None):
        self._bot = bot
        self._settings = settings or get_settings()
        self._scheduler = AsyncIOScheduler(timezone="UTC")
        self._running = False

    # ── Public interface ──────────────────────────────────────────────────────

    def start(self) -> None:
        """Register all jobs and start the scheduler."""
        if self._running:
            logger.warning("ReminderScheduler already running — skipping start()")
            return

        self._register_jobs()
        self._scheduler.start()
        self._running = True
        logger.info("ReminderScheduler started — jobs: %s",
                    [j.id for j in self._scheduler.get_jobs()])

    def shutdown(self, wait: bool = False) -> None:
        """Stop the scheduler gracefully."""
        if self._running:
            self._scheduler.shutdown(wait=wait)
            self._running = False
            logger.info("ReminderScheduler shut down.")

    @property
    def is_running(self) -> bool:
        return self._running

    # ── Job registration ──────────────────────────────────────────────────────

    def _register_jobs(self) -> None:
        s = self._settings

        # 1. Daily reminders — fires at configured hour:minute every day
        self._scheduler.add_job(
            self._job_daily_reminders,
            trigger=CronTrigger(hour=s.reminder_daily_hour, minute=s.reminder_daily_minute),
            id="daily_reminders",
            name="Daily progress reminders",
            replace_existing=True,
            misfire_grace_time=300,
        )

        # 2. Escalation reminders — 18:00 daily for assignments due in ≤2 days
        self._scheduler.add_job(
            self._job_escalation_reminders,
            trigger=CronTrigger(hour=18, minute=0),
            id="escalation_reminders",
            name="Escalation reminders (≤2 days left)",
            replace_existing=True,
            misfire_grace_time=300,
        )

        # 3. Final warning — 08:00 daily for assignments due today
        self._scheduler.add_job(
            self._job_final_warning,
            trigger=CronTrigger(hour=8, minute=0),
            id="final_warning",
            name="Final warning (due today)",
            replace_existing=True,
            misfire_grace_time=300,
        )

        # 4. Overdue check — every 6 hours, teacher notification
        self._scheduler.add_job(
            self._job_overdue_check,
            trigger=IntervalTrigger(hours=6),
            id="overdue_check",
            name="Overdue assignment check",
            replace_existing=True,
            misfire_grace_time=600,
        )

        # 5. Teacher weekly digest — Monday at 08:00
        self._scheduler.add_job(
            self._job_teacher_digest,
            trigger=CronTrigger(day_of_week="mon", hour=8, minute=0),
            id="teacher_digest",
            name="Weekly teacher digest",
            replace_existing=True,
            misfire_grace_time=600,
        )

    # ── Job implementations ───────────────────────────────────────────────────

    async def _job_daily_reminders(self) -> None:
        """Send daily progress nudges to all students with pending/in-progress work."""
        logger.info("[Scheduler] Running job: daily_reminders")
        try:
            async with get_async_session() as db:
                llm = get_llm_provider()
                agent = ReminderAgent(llm, db)
                await agent.process_due_reminders(self._bot, reminder_type="daily")
        except Exception as exc:
            logger.exception(f"[Scheduler] daily_reminders failed: {exc}")

    async def _job_escalation_reminders(self) -> None:
        """Send escalation reminders for assignments due within the escalation window."""
        logger.info("[Scheduler] Running job: escalation_reminders")
        try:
            async with get_async_session() as db:
                llm = get_llm_provider()
                agent = ReminderAgent(llm, db)
                await agent.process_due_reminders(self._bot, reminder_type="escalation")
        except Exception as exc:
            logger.exception(f"[Scheduler] escalation_reminders failed: {exc}")

    async def _job_final_warning(self) -> None:
        """Send final warnings for assignments due today."""
        logger.info("[Scheduler] Running job: final_warning")
        try:
            async with get_async_session() as db:
                llm = get_llm_provider()
                agent = ReminderAgent(llm, db)
                await agent.process_due_reminders(self._bot, reminder_type="final_warning")
        except Exception as exc:
            logger.exception(f"[Scheduler] final_warning failed: {exc}")

    async def _job_overdue_check(self) -> None:
        """Notify teachers about overdue assignments every 6 hours."""
        logger.info("[Scheduler] Running job: overdue_check")
        try:
            async with get_async_session() as db:
                llm = get_llm_provider()
                agent = ReminderAgent(llm, db)
                await agent.process_due_reminders(self._bot, reminder_type="overdue")
        except Exception as exc:
            logger.exception(f"[Scheduler] overdue_check failed: {exc}")

    async def _job_teacher_digest(self) -> None:
        """
        Send a weekly class digest to every active teacher on Monday morning.
        Iterates all teachers and calls SummariserAgent.generate_teacher_digest.
        """
        logger.info("[Scheduler] Running job: teacher_digest")
        try:
            async with get_async_session() as db:
                result = await db.execute(
                    select(User).where(User.role == "teacher", User.is_active == True)
                )
                teachers = result.scalars().all()

                llm = get_llm_provider()
                agent = SummariserAgent(llm, db)

                for teacher in teachers:
                    try:
                        digest = await agent.generate_teacher_digest(teacher.telegram_id)
                        header = "📊 *Weekly Class Digest*\n\n"
                        await self._bot.send_message(
                            chat_id=teacher.telegram_id,
                            text=header + digest,
                            parse_mode="Markdown",
                        )
                        logger.info(f"[Scheduler] Sent weekly digest to teacher {teacher.telegram_id}")
                    except Exception as exc:
                        logger.warning(
                            f"[Scheduler] Failed to send digest to teacher {teacher.telegram_id}: {exc}"
                        )
        except Exception as exc:
            logger.exception(f"[Scheduler] teacher_digest failed: {exc}")
