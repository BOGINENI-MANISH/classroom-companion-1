import json
from typing import Optional

from loguru import logger
from sqlalchemy import select
from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Update,
)
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from agents.intent_agent import IntentAgent
from agents.student_agent import StudentAgent
from agents.summariser_agent import SummariserAgent
from agents.teacher_agent import TeacherAgent
from bot.middleware import BotMiddleware, generate_invite_code
from config import Settings
from database.database import get_async_session
from database.models import Assignment, ConversationState, TeacherStudentLink, User
from llm.provider import get_llm_provider

# ── Conversation state constants ──────────────────────────────────────────────
REGISTER_ROLE = 0
REGISTER_CODE = 1
AWAITING_FEEDBACK = 2


# ── /start ────────────────────────────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    tg_user = update.effective_user
    if not tg_user:
        return

    async with get_async_session() as db:
        result = await db.execute(
            select(User).where(User.telegram_id == tg_user.id)
        )
        user = result.scalar_one_or_none()

        if user and user.role in ("teacher", "student"):
            role_label = "Teacher" if user.role == "teacher" else "Student"
            await update.message.reply_text(
                f"👋 Welcome back, *{user.full_name}*! ({role_label})\n\n"
                f"Use /help to see available commands.",
                parse_mode="Markdown",
            )
            return

    # New user — show role selection
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("👩‍🏫 I'm a Teacher", callback_data="role_teacher"),
            InlineKeyboardButton("🎓 I'm a Student", callback_data="role_student"),
        ]
    ])
    await update.message.reply_text(
        "🎓 Welcome to *Classroom Companion*!\n\n"
        "I help teachers assign work and students track it — all via Telegram.\n\n"
        "First, tell me your role:",
        reply_markup=keyboard,
        parse_mode="Markdown",
    )


# ── /help ─────────────────────────────────────────────────────────────────────

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    tg_user = update.effective_user
    if not tg_user:
        return

    async with get_async_session() as db:
        result = await db.execute(
            select(User).where(User.telegram_id == tg_user.id)
        )
        user = result.scalar_one_or_none()

    if user and user.role == "teacher":
        text = (
            "👩‍🏫 *Teacher Commands*\n\n"
            "📌 *Assign work*: Just type naturally, e.g.:\n"
            "  _'Assign Riya a 500-word essay on photosynthesis, due in 3 days'_\n\n"
            "📊 */status* — View all students & their assignment statuses\n\n"
            "❓ *Ask about a student*: Type naturally, e.g.:\n"
            "  _'How is Riya doing this week?'_\n\n"
            "💬 *Give feedback*: After a student submits, I'll prompt you here\n\n"
            "🔑 */mycode* — Show your invite code for students"
        )
    elif user and user.role == "student":
        text = (
            "🎓 *Student Commands*\n\n"
            "📝 *Report progress*: Just type, e.g.:\n"
            "  _'I've done the first two paragraphs'_\n\n"
            "✅ *Submit work*: Type your submission or send a file/photo\n"
            "  _'All done! Here is my essay...'_\n\n"
            "📋 */mystatus* — See all your active assignments\n\n"
            "🔗 */link* — Link to a teacher using their invite code"
        )
    else:
        text = (
            "👋 Use /start to register and get started!\n\n"
            "I'm Classroom Companion — an AI-powered assignment tracker."
        )

    await update.message.reply_text(text, parse_mode="Markdown")


# ── /status (teachers) ────────────────────────────────────────────────────────

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    tg_user = update.effective_user
    if not tg_user:
        return

    async with get_async_session() as db:
        llm = get_llm_provider()
        agent = SummariserAgent(llm, db)
        digest = await agent.generate_teacher_digest(tg_user.id)

    await update.message.reply_text(digest, parse_mode="Markdown")


# ── /mystatus (students) ──────────────────────────────────────────────────────

async def mystatus_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    tg_user = update.effective_user
    if not tg_user:
        return

    async with get_async_session() as db:
        result = await db.execute(
            select(User).where(User.telegram_id == tg_user.id, User.role == "student")
        )
        student = result.scalar_one_or_none()

        if not student:
            await update.message.reply_text(
                "❌ You are not registered as a student. Use /start to register."
            )
            return

        result = await db.execute(
            select(Assignment).where(Assignment.student_id == student.id)
            .order_by(Assignment.due_date.asc())
        )
        assignments = result.scalars().all()

    if not assignments:
        await update.message.reply_text(
            "📋 You have no assignments yet. Your teacher will assign work soon!"
        )
        return

    from datetime import datetime
    lines = ["📋 *Your Assignments*\n"]
    for a in assignments:
        days_left = (a.due_date - datetime.utcnow()).days
        status_emoji = {
            "pending": "📝", "in_progress": "🔄",
            "submitted": "✅", "reviewed": "🌟",
        }.get(a.status, "❓")
        if days_left < 0 and a.status not in ("submitted", "reviewed"):
            timing = f"⚠️ Overdue by {abs(days_left)}d"
        elif days_left == 0:
            timing = "⚠️ Due TODAY"
        else:
            timing = f"{days_left} day(s) left"
        lines.append(f"{status_emoji} *{a.title}*")
        lines.append(f"   Due: {a.due_date.strftime('%d %b %Y')} — {timing}")
        lines.append(f"   Status: {a.status.replace('_', ' ').title()}\n")

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


# ── /mycode (teachers) ────────────────────────────────────────────────────────

async def mycode_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    tg_user = update.effective_user
    if not tg_user:
        return
    async with get_async_session() as db:
        result = await db.execute(
            select(User).where(User.telegram_id == tg_user.id, User.role == "teacher")
        )
        teacher = result.scalar_one_or_none()

    if not teacher:
        await update.message.reply_text("❌ This command is for teachers only.")
        return

    await update.message.reply_text(
        f"🔑 Your invite code: `{teacher.invite_code}`\n\n"
        "Share this with your students so they can link to your classroom.",
        parse_mode="Markdown",
    )


# ── /link (students) ─────────────────────────────────────────────────────────

async def link_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    tg_user = update.effective_user
    if not tg_user:
        return
    await update.message.reply_text(
        "🔗 Please enter your teacher's invite code to link your account:"
    )
    # Store flag so the next message is treated as invite code
    context.user_data["awaiting_invite_code"] = True


# ── Callback query handler (inline buttons) ───────────────────────────────────

async def handle_callback_query(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    query = update.callback_query
    await query.answer()
    data = query.data or ""
    tg_user = update.effective_user

    if data == "role_teacher":
        await handle_teacher_registration(update, context)
    elif data == "role_student":
        await update.callback_query.edit_message_text(
            "🎓 Please enter your teacher's invite code to link your account:"
        )
        context.user_data["awaiting_invite_code"] = True
    elif data.startswith("confirm_submit_"):
        assignment_id = int(data.split("_")[-1])
        async with get_async_session() as db:
            llm = get_llm_provider()
            agent = StudentAgent(llm, db)
            response = await agent.handle_submission(tg_user.id, "[Submission confirmed]")
        await query.edit_message_text(response.message, parse_mode="Markdown")
        if response.notify_telegram_id and response.notification_message:
            await context.bot.send_message(
                chat_id=response.notify_telegram_id,
                text=response.notification_message,
                parse_mode="Markdown",
            )
    elif data == "cancel_submit":
        await query.edit_message_text("❌ Submission cancelled.")


# ── Teacher registration ──────────────────────────────────────────────────────

async def handle_teacher_registration(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    tg_user = update.effective_user
    if not tg_user:
        return

    full_name = tg_user.full_name or f"Teacher_{tg_user.id}"
    handle = f"@{tg_user.username}" if tg_user.username else None
    invite_code = generate_invite_code(8)

    async with get_async_session() as db:
        result = await db.execute(
            select(User).where(User.telegram_id == tg_user.id)
        )
        existing = result.scalar_one_or_none()

        if existing:
            existing.role = "teacher"
            existing.invite_code = invite_code
            existing.telegram_handle = handle
            db.add(existing)
        else:
            db.add(User(
                telegram_id=tg_user.id,
                full_name=full_name,
                telegram_handle=handle,
                role="teacher",
                invite_code=invite_code,
            ))

        # Ensure conversation state exists
        cs_result = await db.execute(
            select(ConversationState).where(ConversationState.telegram_id == tg_user.id)
        )
        if not cs_result.scalar_one_or_none():
            db.add(ConversationState(telegram_id=tg_user.id, state="idle"))
        await db.flush()

    msg = (
        f"👩‍🏫 Welcome, *{full_name}*!\n\n"
        f"You're registered as a teacher. 🎉\n\n"
        f"🔑 Your invite code: `{invite_code}`\n\n"
        "Share this with your students so they can join your classroom.\n\n"
        "To assign work, just type naturally:\n"
        "_'Assign Riya a 500-word essay on photosynthesis, due in 3 days'_"
    )

    if update.callback_query:
        await update.callback_query.edit_message_text(msg, parse_mode="Markdown")
    else:
        await update.message.reply_text(msg, parse_mode="Markdown")


# ── Student registration ──────────────────────────────────────────────────────

async def handle_student_registration(
    update: Update, context: ContextTypes.DEFAULT_TYPE, invite_code: str
) -> None:
    tg_user = update.effective_user
    if not tg_user:
        return

    full_name = tg_user.full_name or f"Student_{tg_user.id}"
    handle = f"@{tg_user.username}" if tg_user.username else None

    async with get_async_session() as db:
        # Validate invite code
        result = await db.execute(
            select(User).where(User.invite_code == invite_code, User.role == "teacher")
        )
        teacher = result.scalar_one_or_none()

        if not teacher:
            await update.message.reply_text(
                "❌ Invalid invite code. Please check with your teacher and try again."
            )
            return

        # Create or update student
        result = await db.execute(
            select(User).where(User.telegram_id == tg_user.id)
        )
        student = result.scalar_one_or_none()

        if not student:
            student = User(
                telegram_id=tg_user.id,
                full_name=full_name,
                telegram_handle=handle,
                role="student",
            )
            db.add(student)
            await db.flush()
        elif student.role == "unknown":
            student.role = "student"
            db.add(student)
            await db.flush()

        # Create link if not already exists
        link_result = await db.execute(
            select(TeacherStudentLink).where(
                TeacherStudentLink.teacher_id == teacher.id,
                TeacherStudentLink.student_id == student.id,
            )
        )
        if not link_result.scalar_one_or_none():
            db.add(TeacherStudentLink(teacher_id=teacher.id, student_id=student.id))

        # Ensure conversation state
        cs_result = await db.execute(
            select(ConversationState).where(ConversationState.telegram_id == tg_user.id)
        )
        if not cs_result.scalar_one_or_none():
            db.add(ConversationState(telegram_id=tg_user.id, state="idle"))
        await db.flush()

        teacher_name = teacher.full_name

    context.user_data.pop("awaiting_invite_code", None)

    await update.message.reply_text(
        f"🎉 You're now linked to *{teacher_name}*!\n\n"
        "You'll receive your assignments here. Use /mystatus to see them anytime.",
        parse_mode="Markdown",
    )

    # Notify teacher
    try:
        await context.bot.send_message(
            chat_id=teacher.telegram_id,
            text=f"🎓 *{full_name}* just joined your classroom!",
            parse_mode="Markdown",
        )
    except Exception as exc:
        logger.warning(f"Failed to notify teacher about new student: {exc}")


# ── Central message router ────────────────────────────────────────────────────

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Route every text message through middleware → state machine → agent."""
    if not update.message or not update.message.text:
        return

    tg_user = update.effective_user
    if not tg_user:
        return

    # Middleware checks
    block_reason = await BotMiddleware.check(update)
    if block_reason == "rate_limited":
        await update.message.reply_text(
            "⚠️ You're sending messages too fast. Please wait a moment."
        )
        return
    elif block_reason == "inactive":
        await update.message.reply_text("❌ Your account has been deactivated.")
        return

    message_text = update.message.text
    tid = tg_user.id

    # Handle pending invite code input
    if context.user_data.get("awaiting_invite_code"):
        await handle_student_registration(update, context, invite_code=message_text.strip())
        return

    async with get_async_session() as db:
        # Get user
        result = await db.execute(select(User).where(User.telegram_id == tid))
        user = result.scalar_one_or_none()

        if not user or user.role == "unknown":
            await update.message.reply_text(
                "👋 Welcome! Please use /start to register first."
            )
            return

        # Get conversation state
        cs_result = await db.execute(
            select(ConversationState).where(ConversationState.telegram_id == tid)
        )
        conv_state = cs_result.scalar_one_or_none()
        current_state = conv_state.state if conv_state else "idle"

        llm = get_llm_provider()

        # ── State: teacher awaiting_feedback ─────────────────────────────────
        if current_state == "awaiting_feedback" and user.role == "teacher":
            context_json = conv_state.context_json if conv_state else None
            assignment_id = None
            if context_json:
                try:
                    ctx = json.loads(context_json)
                    assignment_id = ctx.get("assignment_id")
                except (json.JSONDecodeError, TypeError):
                    pass

            if assignment_id:
                agent = TeacherAgent(llm, db)
                response = await agent.handle_feedback(tid, assignment_id, message_text)
            else:
                await update.message.reply_text(
                    "⚠️ I lost track of which assignment this feedback is for. "
                    "Please wait for the next student submission."
                )
                return

        # ── State: awaiting_submission (student) ─────────────────────────────
        elif current_state == "awaiting_submission" and user.role == "student":
            agent = StudentAgent(llm, db)
            response = await agent.handle_submission(tid, message_text)

        # ── Default: classify intent → route to agent ─────────────────────────
        else:
            intent_agent = IntentAgent(llm, db)
            intent_result = await intent_agent.classify(tid, message_text, role=user.role)
            intent = intent_result.intent

            # Handle registration intents
            if intent == "register_teacher":
                await handle_teacher_registration(update, context)
                return
            elif intent == "register_student":
                await update.message.reply_text(
                    "🔗 Please enter your teacher's invite code:"
                )
                context.user_data["awaiting_invite_code"] = True
                return
            elif intent == "help":
                await help_command(update, context)
                return

            # Route to the correct agent
            if user.role == "teacher":
                if intent in ("assign_work", "teacher_query", "request_summary", "feedback"):
                    agent = TeacherAgent(llm, db)
                    response = await agent.handle(tid, message_text, intent=intent)
                else:
                    await update.message.reply_text(
                        "I'm not sure what you'd like to do. Try:\n"
                        "• Assigning work: 'Assign Riya an essay on photosynthesis, due in 3 days'\n"
                        "• Asking about a student: 'How is Riya doing?'\n"
                        "• Getting a class summary: /status"
                    )
                    return
            elif user.role == "student":
                agent = StudentAgent(llm, db)
                response = await agent.handle(
                    tid, message_text, intent=intent
                )
            else:
                await update.message.reply_text(
                    "👋 Please use /start to complete your registration."
                )
                return

        # ── Send response and handle notifications ────────────────────────────
        if response.message:
            await update.message.reply_text(response.message, parse_mode="Markdown")

        # Update conversation state if transition requested
        if response.state_transition and conv_state:
            conv_state.state = response.state_transition
            db.add(conv_state)
            await db.flush()

        # Send notification to the other party
        if response.notify_telegram_id:
            await _send_bot_notification(context, response.notify_telegram_id, response)

        # If teacher needs to be put into awaiting_feedback state, update it
        if (
            response.action == "notify_teacher"
            and response.notify_telegram_id
            and user.role == "student"
        ):
            # Check if teacher state needs to be set (done inside StudentAgent already,
            # but update it here too in case the session was separate)
            pass


async def _send_bot_notification(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    response,
) -> None:
    try:
        if response.notification_file_type == "photo" and response.notification_file_id:
            await context.bot.send_photo(
                chat_id=chat_id,
                photo=response.notification_file_id,
                caption=response.notification_caption or response.notification_message,
                parse_mode="Markdown",
            )
            return
        if response.notification_file_type == "document" and response.notification_file_id:
            await context.bot.send_document(
                chat_id=chat_id,
                document=response.notification_file_id,
                caption=response.notification_caption or response.notification_message,
                parse_mode="Markdown",
            )
            return
        if response.notification_file_type == "voice" and response.notification_file_id:
            await context.bot.send_voice(
                chat_id=chat_id,
                voice=response.notification_file_id,
                caption=response.notification_caption or response.notification_message,
                parse_mode="Markdown",
            )
            return
        if response.notification_message:
            await context.bot.send_message(
                chat_id=chat_id,
                text=response.notification_message,
                parse_mode="Markdown",
            )
    except Exception as exc:
        logger.error(f"Failed to send notification to {chat_id}: {exc}")


# ── Document / Photo / Voice handlers ────────────────────────────────────────

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle file submissions from students."""
    tg_user = update.effective_user
    if not tg_user or not update.message or not update.message.document:
        return

    doc = update.message.document
    caption = update.message.caption or ""

    async with get_async_session() as db:
        llm = get_llm_provider()
        agent = StudentAgent(llm, db)
        response = await agent.handle_submission(
            tg_user.id,
            message=caption,
            file_id=doc.file_id,
            file_type="document",
            file_name=doc.file_name,
        )

    await update.message.reply_text(response.message, parse_mode="Markdown")
    if response.notify_telegram_id:
        await _send_bot_notification(context, response.notify_telegram_id, response)


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle photo submissions — use the largest available photo size."""
    tg_user = update.effective_user
    if not tg_user or not update.message or not update.message.photo:
        return

    # Largest photo is the last in the list
    photo = update.message.photo[-1]
    caption = update.message.caption or ""

    async with get_async_session() as db:
        llm = get_llm_provider()
        agent = StudentAgent(llm, db)
        response = await agent.handle_submission(
            tg_user.id,
            message=caption,
            file_id=photo.file_id,
            file_type="photo",
        )

    await update.message.reply_text(response.message, parse_mode="Markdown")
    if response.notify_telegram_id:
        await _send_bot_notification(context, response.notify_telegram_id, response)


async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle voice note submissions."""
    tg_user = update.effective_user
    if not tg_user or not update.message or not update.message.voice:
        return

    voice = update.message.voice

    async with get_async_session() as db:
        llm = get_llm_provider()
        agent = StudentAgent(llm, db)
        response = await agent.handle_voice_submission(
            tg_user.id,
            file_id=voice.file_id,
            duration=voice.duration,
        )

    await update.message.reply_text(response.message, parse_mode="Markdown")
    if response.notify_telegram_id:
        await _send_bot_notification(context, response.notify_telegram_id, response)


# ── Application factory ───────────────────────────────────────────────────────

def create_application(settings: Settings) -> Application:
    """
    Build and return the configured Telegram Application.
    Handler registration order: specific commands first, then general messages.
    """
    app = Application.builder().token(settings.telegram_bot_token).build()

    # Command handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("status", status_command))
    app.add_handler(CommandHandler("mystatus", mystatus_command))
    app.add_handler(CommandHandler("mycode", mycode_command))
    app.add_handler(CommandHandler("link", link_command))

    # Callback query handler (inline keyboard buttons)
    app.add_handler(CallbackQueryHandler(handle_callback_query))

    # Media handlers (before generic text handler)
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))

    # Central text message router (must be last)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("Telegram Application configured with all handlers.")
    return app
