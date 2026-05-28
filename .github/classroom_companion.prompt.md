# 🤖 VS Code Copilot Master Prompt — "Classroom Companion" Telegram Bot
## SIM Engineering Take-Home Assignment — Full Implementation Guide

> **How to use this prompt:**
> Open VS Code with GitHub Copilot enabled. Open a new Chat panel (Ctrl+Shift+I or Cmd+Shift+I).
> Paste each numbered section as a separate Copilot Chat message in order.
> After each section, review the generated code, then proceed to the next.
> Use `@workspace` context where indicated so Copilot can see previously generated files.

---

## ═══════════════════════════════════════════════
## SECTION 0 — MASTER CONTEXT (Paste this FIRST, keep it pinned)
## ═══════════════════════════════════════════════

```
You are helping me build "Classroom Companion" — a production-grade AI-powered Telegram bot for 
assignment management between Teachers and Students. This is an engineering interview assignment 
for Super Intelli Machines (SIM).

FULL TECH STACK (non-negotiable):
- Language: Python 3.11+
- LLM: Grok via xAI API (OpenAI-compatible SDK, base_url="https://api.x.ai/v1", model="grok-3")
- Bot Framework: python-telegram-bot v20+ (async, webhook-based locally via ngrok)
- Backend API: FastAPI (async)
- Database: SQLite with SQLAlchemy 2.0 (async engine)
- Scheduler: APScheduler 3.x (AsyncIOScheduler)
- Frontend: Vanilla HTML + CSS + Vanilla JS (no frameworks)
- Testing: pytest + pytest-asyncio + httpx (async test client) + unittest.mock
- Local dev: ngrok for Telegram webhook tunneling

MULTI-AGENT ARCHITECTURE (Single LLM with Tools pattern):
- IntentAgent: classifies incoming messages (assignment | progress | completion | feedback | query | unknown)
- TeacherAgent: handles all teacher-side conversations (assign, collect feedback, answer "how is X doing?")
- StudentAgent: handles all student-side conversations (acknowledge, capture progress, collect submission)
- ReminderAgent: driven by APScheduler — decides when/how to nudge students intelligently
- SummariserAgent: generates proactive status digests for teachers

PROVIDER ABSTRACTION (CRITICAL — must be swappable live in interview):
- All LLM calls go through a single LLMProvider class in llm/provider.py
- Provider is selected from env var: LLM_PROVIDER=grok|openai|gemini
- For Grok: openai SDK with base_url="https://api.x.ai/v1"
- For OpenAI: openai SDK default
- Switching provider = change one env var, zero code changes

KEY CONSTRAINTS:
- All agents must be clearly separated from Telegram transport and FastAPI routes
- APScheduler runs inside the same Python process
- SQLite DB file persists across restarts (no in-memory)
- Secrets: only via .env file (never hardcoded)
- Commits: each file is a logical commit unit
- README must include architecture diagram (ASCII), all setup steps, agent design, prompt strategy
- End-to-end code coverage: unit tests for every agent, integration tests with seeded DB
- Bonus features to implement: file/photo submission, teacher "how is X doing?" LLM summary, 
  unit+integration tests, deployed locally with ngrok
```

---

## ═══════════════════════════════════════════════
## SECTION 1 — PROJECT SCAFFOLD & CONFIGURATION
## ═══════════════════════════════════════════════

```
@workspace Generate the complete project scaffold for "Classroom Companion". Create every file 
listed below with correct content. Do NOT leave placeholders — write real, working code.

PROJECT STRUCTURE (create exactly this):
classroom-companion/
├── .env.example
├── .gitignore
├── requirements.txt
├── main.py
├── config.py
├── database/
│   ├── __init__.py
│   ├── models.py
│   ├── database.py
│   └── seed.py
├── llm/
│   ├── __init__.py
│   ├── provider.py
│   └── tools.py
├── agents/
│   ├── __init__.py
│   ├── base_agent.py
│   ├── intent_agent.py
│   ├── teacher_agent.py
│   ├── student_agent.py
│   ├── reminder_agent.py
│   └── summariser_agent.py
├── bot/
│   ├── __init__.py
│   ├── handlers.py
│   └── middleware.py
├── api/
│   ├── __init__.py
│   ├── main.py
│   └── routes/
│       ├── __init__.py
│       ├── health.py
│       ├── teacher.py
│       └── student.py
├── scheduler/
│   ├── __init__.py
│   └── reminder_scheduler.py
├── static/
│   ├── teacher/
│   │   ├── index.html
│   │   ├── style.css
│   │   └── app.js
│   └── student/
│       ├── index.html
│       ├── style.css
│       └── app.js
└── tests/
    ├── __init__.py
    ├── conftest.py
    ├── fixtures/
    │   ├── __init__.py
    │   └── test_data.py
    ├── unit/
    │   ├── __init__.py
    │   ├── test_intent_agent.py
    │   ├── test_teacher_agent.py
    │   ├── test_student_agent.py
    │   ├── test_reminder_agent.py
    │   └── test_summariser_agent.py
    └── integration/
        ├── __init__.py
        ├── test_api_teacher.py
        ├── test_api_student.py
        └── test_bot_flows.py

FILE CONTENTS:

--- .env.example ---
TELEGRAM_BOT_TOKEN=your_telegram_bot_token_here
NGROK_AUTH_TOKEN=your_ngrok_auth_token_here
WEBHOOK_BASE_URL=https://your-ngrok-url.ngrok.io

# LLM Configuration
LLM_PROVIDER=grok
GROK_API_KEY=your_grok_api_key_here
OPENAI_API_KEY=your_openai_api_key_here
GEMINI_API_KEY=your_gemini_api_key_here
LLM_MODEL=grok-3
LLM_TEMPERATURE=0.3
LLM_MAX_TOKENS=1024

# Database
DATABASE_URL=sqlite+aiosqlite:///./classroom_companion.db
TEST_DATABASE_URL=sqlite+aiosqlite:///./test_classroom_companion.db

# App
APP_HOST=0.0.0.0
APP_PORT=8000
DEBUG=true
LOG_LEVEL=INFO

# Scheduler
REMINDER_CHECK_INTERVAL_MINUTES=60
REMINDER_DAILY_HOUR=9
REMINDER_DAILY_MINUTE=0
ESCALATION_DAYS_BEFORE_DEADLINE=2

--- .gitignore ---
__pycache__/
*.py[cod]
*.env
*.db
*.db-shm
*.db-wal
.venv/
venv/
.pytest_cache/
htmlcov/
.coverage
dist/
build/
*.egg-info/
ngrok
ngrok.exe

--- requirements.txt ---
# Core
fastapi==0.111.0
uvicorn[standard]==0.29.0
python-telegram-bot[webhooks]==21.3
aiohttp==3.9.5
httpx==0.27.0

# Database
sqlalchemy==2.0.30
aiosqlite==0.20.0
alembic==1.13.1

# LLM
openai==1.30.1

# Scheduler
apscheduler==3.10.4

# Config
python-dotenv==1.0.1
pydantic==2.7.1
pydantic-settings==2.3.0

# Testing
pytest==8.2.2
pytest-asyncio==0.23.7
pytest-cov==5.0.0
respx==0.21.1
factory-boy==3.3.0
freezegun==1.5.1

# Utilities
python-multipart==0.0.9
loguru==0.7.2

--- config.py ---
Write a full Pydantic BaseSettings class called Settings that reads all env vars from .env.example.
Include:
- telegram_bot_token: str
- webhook_base_url: str
- ngrok_auth_token: str
- llm_provider: str = "grok"
- grok_api_key: str = ""
- openai_api_key: str = ""
- gemini_api_key: str = ""
- llm_model: str = "grok-3"
- llm_temperature: float = 0.3
- llm_max_tokens: int = 1024
- database_url: str
- test_database_url: str
- app_host: str = "0.0.0.0"
- app_port: int = 8000
- debug: bool = False
- log_level: str = "INFO"
- reminder_check_interval_minutes: int = 60
- reminder_daily_hour: int = 9
- reminder_daily_minute: int = 0
- escalation_days_before_deadline: int = 2
Use model_config = SettingsConfigDict(env_file=".env", case_sensitive=False)
Expose a cached settings singleton: get_settings() -> Settings using lru_cache.
```

---

## ═══════════════════════════════════════════════
## SECTION 2 — DATABASE MODELS & SEEDING
## ═══════════════════════════════════════════════

```
@workspace Generate database/models.py and database/database.py and database/seed.py.

--- database/models.py ---
Use SQLAlchemy 2.0 declarative ORM with async support. Define these tables:

class User(Base):
    __tablename__ = "users"
    id: int (PK, autoincrement)
    telegram_id: int (unique, not null) — Telegram user ID
    telegram_handle: str (nullable) — @username
    full_name: str (not null)
    role: str (not null) — "teacher" or "student"
    invite_code: str (unique, nullable) — teacher-generated code for student onboarding
    created_at: datetime (default=utcnow)
    is_active: bool (default=True)

class TeacherStudentLink(Base):
    __tablename__ = "teacher_student_links"
    id: int (PK)
    teacher_id: int (FK → users.id)
    student_id: int (FK → users.id)
    linked_at: datetime (default=utcnow)
    teacher: relationship → User
    student: relationship → User
    UniqueConstraint on (teacher_id, student_id)

class Assignment(Base):
    __tablename__ = "assignments"
    id: int (PK)
    teacher_id: int (FK → users.id)
    student_id: int (FK → users.id)
    title: str (not null)
    description: str (not null) — parsed from teacher's NL instruction
    raw_instruction: str (not null) — original teacher text
    due_date: datetime (not null)
    status: str (not null, default="pending") — "pending"|"in_progress"|"submitted"|"reviewed"
    created_at: datetime (default=utcnow)
    updated_at: datetime (default=utcnow, onupdate=utcnow)
    teacher: relationship → User
    student: relationship → User
    reminders: relationship → list[Reminder]
    progress_updates: relationship → list[ProgressUpdate]
    submission: relationship → Submission (uselist=False)

class ProgressUpdate(Base):
    __tablename__ = "progress_updates"
    id: int (PK)
    assignment_id: int (FK → assignments.id)
    student_id: int (FK → users.id)
    message: str (not null) — student's raw NL update
    interpreted_status: str (not null) — LLM-parsed: "not_started"|"in_progress"|"nearly_done"|"completed"
    created_at: datetime (default=utcnow)

class Submission(Base):
    __tablename__ = "submissions"
    id: int (PK)
    assignment_id: int (FK → assignments.id, unique)
    student_id: int (FK → users.id)
    text_content: str (nullable) — typed submission
    file_id: str (nullable) — Telegram file_id
    file_type: str (nullable) — "document"|"photo"|"voice"
    file_name: str (nullable)
    transcript: str (nullable) — voice note transcription
    submitted_at: datetime (default=utcnow)

class Feedback(Base):
    __tablename__ = "feedbacks"
    id: int (PK)
    assignment_id: int (FK → assignments.id, unique)
    teacher_id: int (FK → users.id)
    raw_feedback: str (not null) — teacher's NL feedback
    formatted_feedback: str (not null) — LLM-formatted friendly version
    created_at: datetime (default=utcnow)

class Reminder(Base):
    __tablename__ = "reminders"
    id: int (PK)
    assignment_id: int (FK → assignments.id)
    student_id: int (FK → users.id)
    sent_at: datetime (default=utcnow)
    reminder_type: str (not null) — "daily"|"escalation"|"final_warning"
    message: str (not null)

class ConversationState(Base):
    __tablename__ = "conversation_states"
    id: int (PK)
    telegram_id: int (unique, not null)
    state: str (not null) — "idle"|"awaiting_assignment_details"|"awaiting_feedback"|"awaiting_submission"
    context_json: str (nullable) — JSON blob for stateful multi-turn context
    updated_at: datetime (default=utcnow, onupdate=utcnow)

--- database/database.py ---
Create async SQLAlchemy engine using aiosqlite.
Functions needed:
- get_engine() → async engine (singleton)
- get_async_session() → AsyncSession context manager
- init_db() → creates all tables using Base.metadata.create_all
- get_db() → FastAPI dependency that yields AsyncSession

--- database/seed.py ---
Create seed_test_data() async function that populates the following test data. 
This enables integration tests to run against real data immediately.

SEED DATA:
Teachers:
  - Teacher 1: telegram_id=100001, full_name="Prof. Sharma", role="teacher", invite_code="SHARMA2024", telegram_handle="@prof_sharma"
  - Teacher 2: telegram_id=100002, full_name="Dr. Patel", role="teacher", invite_code="PATEL2024", telegram_handle="@dr_patel"

Students:
  - Student 1: telegram_id=200001, full_name="Riya Singh", role="student", telegram_handle="@riya_singh"
  - Student 2: telegram_id=200002, full_name="Arjun Mehta", role="student", telegram_handle="@arjun_mehta"
  - Student 3: telegram_id=200003, full_name="Priya Nair", role="student", telegram_handle="@priya_nair"
  - Student 4: telegram_id=200004, full_name="Karan Gupta", role="student", telegram_handle="@karan_gupta"

Teacher-Student Links:
  - Sharma → Riya, Arjun
  - Patel → Priya, Karan

Assignments (use realistic due dates relative to now using datetime.utcnow()):
  - Assignment 1: Sharma → Riya, "Write a 500-word essay on photosynthesis", due_date=utcnow()+3days, status="in_progress"
  - Assignment 2: Sharma → Arjun, "Solve 10 quadratic equations", due_date=utcnow()+1day, status="pending" (escalation candidate)
  - Assignment 3: Patel → Priya, "Create a poster on water conservation", due_date=utcnow()+5days, status="submitted"
  - Assignment 4: Patel → Karan, "Write a book report on Animal Farm", due_date=utcnow()-1day, status="submitted" (past due)

ProgressUpdates:
  - Assignment 1/Riya: "done 2 paragraphs, working on conclusion", interpreted_status="in_progress"
  - Assignment 3/Priya: "completed the poster", interpreted_status="completed"

Submissions:
  - Assignment 3/Priya: text_content="[Poster submitted via file]", file_type="photo"
  - Assignment 4/Karan: text_content="Here is my book report on Animal Farm...", file_type=None

Feedbacks:
  - Assignment 4/Karan: raw_feedback="Good work but needs more analysis of the allegory", 
    formatted_feedback="Great effort Karan! Your report showed solid understanding. To make it even better, try exploring the allegorical meaning behind each character a little more deeply. Overall, really good work! 🌟"

ConversationStates:
  - All users start as "idle"

Print a summary after seeding: "✅ Seeded X teachers, Y students, Z assignments"
Also create a clear_test_data() async function that deletes all rows in reverse FK order.
```

---

## ═══════════════════════════════════════════════
## SECTION 3 — LLM PROVIDER & TOOL DEFINITIONS
## ═══════════════════════════════════════════════

```
@workspace Generate llm/provider.py and llm/tools.py.

--- llm/provider.py ---
Create a swappable LLM provider abstraction. 

class LLMProvider:
    """
    Provider-agnostic wrapper. Switch providers by changing LLM_PROVIDER env var.
    Supported: grok, openai, gemini (gemini uses openai-compat endpoint)
    """
    
    def __init__(self, settings: Settings):
        self.settings = settings
        self.client = self._build_client()
        self.model = settings.llm_model
    
    def _build_client(self) -> openai.AsyncOpenAI:
        """Returns an AsyncOpenAI client configured for the selected provider."""
        provider = self.settings.llm_provider.lower()
        if provider == "grok":
            return AsyncOpenAI(
                api_key=self.settings.grok_api_key,
                base_url="https://api.x.ai/v1"
            )
        elif provider == "openai":
            return AsyncOpenAI(api_key=self.settings.openai_api_key)
        elif provider == "gemini":
            return AsyncOpenAI(
                api_key=self.settings.gemini_api_key,
                base_url="https://generativelanguage.googleapis.com/v1beta/openai/"
            )
        else:
            raise ValueError(f"Unknown LLM provider: {provider}")
    
    async def complete(
        self,
        system_prompt: str,
        user_message: str,
        tools: list[dict] | None = None,
        tool_choice: str = "auto",
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> ChatCompletion:
        """Core completion method used by all agents."""
        kwargs = {
            "model": self.model,
            "temperature": temperature or self.settings.llm_temperature,
            "max_tokens": max_tokens or self.settings.llm_max_tokens,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
        }
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = tool_choice
        
        response = await self.client.chat.completions.create(**kwargs)
        return response
    
    async def complete_with_history(
        self,
        system_prompt: str,
        messages: list[dict],
        tools: list[dict] | None = None,
    ) -> ChatCompletion:
        """Multi-turn completion with full message history."""
        # Implementation here
        pass

Expose get_llm_provider() as a cached singleton factory function.

--- llm/tools.py ---
Define all OpenAI-format tool schemas used by agents.

Tools to define (each as a dict following OpenAI function-calling schema):

1. parse_assignment_instruction
   Description: "Parse a teacher's natural language assignment instruction into structured fields"
   Parameters:
     - student_name: str — name of the student being assigned work
     - title: str — brief assignment title (max 60 chars)
     - description: str — full assignment description
     - due_days: int — number of days from today (1-30)
     - word_count: int | None — word/page count if mentioned
   
2. classify_student_message
   Description: "Classify a student's incoming message intent and extract structured info"
   Parameters:
     - intent: enum["progress_update"|"completion"|"question"|"submission_text"|"other"]
     - progress_description: str — what the student has done
     - completion_confirmed: bool — did student explicitly say they are done?
     - has_attachment: bool — did message mention a file/photo?
     - interpreted_status: enum["not_started"|"in_progress"|"nearly_done"|"completed"]
   
3. generate_assignment_message
   Description: "Generate a friendly assignment notification message for a student"
   Parameters:
     - student_name: str
     - assignment_title: str
     - assignment_description: str
     - due_date_str: str — human-readable due date string
     - tone: enum["warm"|"encouraging"|"urgent"]
   Returns: generated_message: str

4. generate_reminder_message
   Description: "Generate an intelligent reminder message for a student"
   Parameters:
     - student_name: str
     - assignment_title: str
     - due_date_str: str
     - days_remaining: int
     - last_progress: str | None
     - reminder_number: int — which reminder (1st, 2nd, 3rd etc.)
   Returns: generated_message: str

5. generate_feedback_message
   Description: "Convert a teacher's raw feedback into a friendly, constructive message for the student"
   Parameters:
     - student_name: str
     - assignment_title: str
     - raw_teacher_feedback: str
   Returns: formatted_message: str

6. generate_status_summary
   Description: "Generate a summary of a student's progress for the teacher"
   Parameters:
     - student_name: str
     - assignment_title: str
     - status: str
     - progress_updates: list[str]
     - due_date_str: str
   Returns: summary_text: str

7. answer_teacher_query
   Description: "Answer a teacher's question about a student using available context"
   Parameters:
     - query: str
     - student_name: str
     - assignments_context: str — JSON summary of student's assignments
   Returns: answer: str

Also create a ToolRegistry class that holds all tool definitions and has:
  - get_tools(names: list[str]) -> list[dict]
  - get_all_tools() -> list[dict]
```

---

## ═══════════════════════════════════════════════
## SECTION 4 — AGENT IMPLEMENTATIONS
## ═══════════════════════════════════════════════

```
@workspace Generate all 5 agent files. Each agent must be fully implemented with real logic.

--- agents/base_agent.py ---
Abstract base class for all agents:

class BaseAgent(ABC):
    def __init__(self, llm: LLMProvider, db: AsyncSession):
        self.llm = llm
        self.db = db
        self.logger = loguru logger
    
    @abstractmethod
    async def handle(self, telegram_id: int, message: str, **kwargs) -> AgentResponse:
        pass
    
    @dataclass
    class AgentResponse:
        message: str           # Text to send back to user
        action: str            # "reply"|"no_reply"|"notify_teacher"|"notify_student"
        notify_telegram_id: int | None = None
        notification_message: str | None = None
        state_transition: str | None = None  # new conversation state
        metadata: dict = field(default_factory=dict)

--- agents/intent_agent.py ---
Classifies incoming message from any user. System prompt must be precise.

SYSTEM PROMPT FOR INTENT AGENT:
"""
You are a message classifier for a classroom assignment management bot. 
Analyze the incoming message and classify it into exactly one intent.

Available intents:
- "register_teacher": User wants to register as a teacher
- "register_student": User wants to link to a teacher (provides invite code)  
- "assign_work": Teacher is assigning work to a student (e.g. "Assign Riya a 500-word essay...")
- "progress_update": Student is reporting progress (e.g. "done 2 paragraphs", "stuck on intro")
- "submission": Student is saying they are done / submitting work
- "feedback": Teacher is providing feedback on a submission
- "teacher_query": Teacher is asking about a student (e.g. "how is Riya doing this week?")
- "request_summary": Teacher wants a status summary of all students
- "help": User needs help or doesn't understand what to do
- "unknown": None of the above

Respond ONLY with a JSON object: {"intent": "...", "confidence": 0.0-1.0, "reasoning": "..."}
"""

class IntentAgent(BaseAgent):
    async def classify(self, telegram_id: int, message: str, role: str) -> IntentResult:
        # Call LLM with intent classification system prompt
        # Parse JSON response
        # Return IntentResult(intent, confidence, reasoning)
        pass

--- agents/teacher_agent.py ---
Handles all teacher-side conversations. CRITICAL: implement all methods fully.

SYSTEM PROMPT FOR TEACHER AGENT:
"""
You are the Teacher Assistant for Classroom Companion. You help teachers assign work, 
collect feedback, and stay informed about student progress.

When a teacher assigns work, extract: student name, assignment description, deadline.
When collecting feedback, transform the teacher's words into encouraging, constructive feedback 
that will motivate the student.
When answering queries about students, synthesize the available information clearly and helpfully.

Always be professional, clear, and efficient. Teachers are busy — keep responses concise.
"""

class TeacherAgent(BaseAgent):
    
    async def handle_assignment_instruction(
        self, teacher_id: int, message: str
    ) -> AgentResponse:
        """
        Flow:
        1. Use parse_assignment_instruction tool to extract structured data
        2. Look up student by name among teacher's linked students
        3. Create Assignment record in DB
        4. Generate assignment message for student using generate_assignment_message tool
        5. Return AgentResponse with action="notify_student" and the student's telegram_id
        6. Confirm to teacher: "✅ Assignment sent to {student_name}! Due: {due_date}"
        """
        pass

    async def handle_feedback(
        self, teacher_id: int, assignment_id: int, raw_feedback: str
    ) -> AgentResponse:
        """
        Flow:
        1. Use generate_feedback_message tool to format feedback
        2. Create Feedback record in DB
        3. Update Assignment status to "reviewed"
        4. Return AgentResponse with action="notify_student" 
        5. Confirm to teacher: "✅ Feedback sent to {student_name}!"
        """
        pass

    async def handle_student_query(
        self, teacher_id: int, message: str
    ) -> AgentResponse:
        """
        Flow:
        1. Extract student name from message
        2. Fetch all assignments + progress updates for that student from DB
        3. Use answer_teacher_query tool with full context JSON
        4. Return the LLM-generated answer
        """
        pass

    async def handle_summary_request(
        self, teacher_id: int
    ) -> AgentResponse:
        """
        Flow:
        1. Fetch all students linked to this teacher
        2. For each student, fetch active assignments + latest progress
        3. Use generate_status_summary tool for each
        4. Compose a formatted summary message
        5. Return AgentResponse
        """
        pass

--- agents/student_agent.py ---
Handles all student-side conversations.

SYSTEM PROMPT FOR STUDENT AGENT:
"""
You are the Student Assistant for Classroom Companion. You help students track their assignments,
report progress, and submit their work.

Be encouraging, friendly, and supportive. Students may feel stressed — your tone should be warm 
and motivating. When a student reports progress, acknowledge it positively.
When they submit work, celebrate their completion enthusiastically.
"""

class StudentAgent(BaseAgent):
    
    async def handle_progress_update(
        self, student_id: int, message: str
    ) -> AgentResponse:
        """
        Flow:
        1. Use classify_student_message tool to parse intent and status
        2. Find student's most recent active assignment
        3. Create ProgressUpdate record in DB
        4. Update Assignment status if needed
        5. Notify teacher with a brief update via generate_status_summary
        6. Reply to student with encouragement
        """
        pass
    
    async def handle_submission(
        self, student_id: int, message: str, 
        file_id: str | None = None,
        file_type: str | None = None,
        file_name: str | None = None,
        voice_transcript: str | None = None,
    ) -> AgentResponse:
        """
        Flow:
        1. Find student's active assignment
        2. Create Submission record (text and/or file)
        3. Update Assignment status to "submitted"
        4. Notify teacher with submission details + prompt for feedback
        5. Change teacher's conversation state to "awaiting_feedback"
        6. Confirm to student: "🎉 Great work! Your submission has been sent to your teacher."
        """
        pass
    
    async def handle_voice_submission(
        self, student_id: int, file_id: str, duration: int
    ) -> AgentResponse:
        """
        Flow:
        1. Download voice note via Telegram Bot API
        2. Transcribe using Whisper or note transcript unavailable
        3. Handle as regular submission with transcript included
        """
        pass

--- agents/reminder_agent.py ---
Driven by APScheduler. Contains the reminder intelligence logic.

REMINDER INTELLIGENCE RULES (implement these exactly):
1. Daily reminders: sent at 9 AM local time, only if assignment is not submitted
2. Escalation trigger: when days_remaining <= 2, switch to twice-daily (9 AM + 6 PM)
3. Final warning: when days_remaining == 0 (due today), send a final warning at 8 AM
4. Never send a reminder if one was already sent within the last 8 hours
5. If a student has reported "nearly_done" status, skip the daily and send a motivational nudge instead
6. Skip reminders on already-submitted assignments
7. Overdue assignments: notify teacher once, then stop student reminders

SYSTEM PROMPT FOR REMINDER AGENT:
"""
You are crafting reminder messages for students about their assignments.
Be encouraging, not nagging. Vary the wording across reminders so they don't feel robotic.
For near-deadline reminders, convey urgency while staying supportive.
Personalize using the student's name and specific assignment details.
"""

class ReminderAgent(BaseAgent):
    
    async def process_due_reminders(self, bot) -> None:
        """
        Called by APScheduler every REMINDER_CHECK_INTERVAL_MINUTES.
        1. Fetch all non-submitted assignments
        2. For each, determine if reminder is needed based on rules above
        3. Generate reminder message using LLM
        4. Send via bot.send_message(student_telegram_id, message)
        5. Log reminder in Reminder table
        """
        pass
    
    async def _should_send_reminder(
        self, assignment: Assignment, last_reminder: Reminder | None
    ) -> tuple[bool, str]:
        """Returns (should_send, reminder_type)"""
        pass
    
    async def _send_overdue_teacher_notification(
        self, assignment: Assignment, bot
    ) -> None:
        """Notify teacher once when an assignment goes overdue."""
        pass

--- agents/summariser_agent.py ---
Generates proactive and on-demand summaries.

SYSTEM PROMPT FOR SUMMARISER AGENT:
"""
You generate clear, actionable status reports about student assignment progress.
For teachers: summarize each student's status concisely. Flag concerns (overdue, no progress).
Use emoji sparingly to improve scannability: ✅ submitted, 🔄 in progress, ⚠️ at risk, ❌ overdue.
Keep each student summary to 2-3 lines max.
"""

class SummariserAgent(BaseAgent):
    
    async def generate_student_summary(
        self, student_id: int, assignment_id: int
    ) -> str:
        """Single assignment summary for teacher notification."""
        pass
    
    async def generate_teacher_digest(
        self, teacher_id: int
    ) -> str:
        """Full digest of all students and their assignments for a teacher."""
        pass
    
    async def answer_student_query_for_teacher(
        self, teacher_id: int, student_name: str, query: str
    ) -> str:
        """LLM-powered answer to teacher's question about a specific student."""
        pass
```

---

## ═══════════════════════════════════════════════
## SECTION 5 — TELEGRAM BOT HANDLERS
## ═══════════════════════════════════════════════

```
@workspace Generate bot/handlers.py and bot/middleware.py — the complete Telegram bot layer.

--- bot/handlers.py ---
Use python-telegram-bot v20 async API. Implement ALL handlers listed below.

IMPORTS AND SETUP:
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ConversationHandler, filters, ContextTypes
)

CONVERSATION STATES (define as module-level constants):
REGISTER_ROLE = 0
REGISTER_CODE = 1
AWAITING_FEEDBACK = 2

COMMAND HANDLERS — implement all:

/start handler:
  - Check if user exists in DB
  - If new: Show welcome message with inline buttons: [👩‍🏫 I'm a Teacher] [🎓 I'm a Student]
  - If exists: Show their dashboard link and available commands

/help handler:
  - Show contextual help based on user role
  - Teacher help: how to assign, request summary, give feedback
  - Student help: how to report progress, submit work

/assign handler (teachers only):
  - Prompt teacher: "Tell me what to assign. Example: 'Assign Riya a 500-word essay on photosynthesis, due in 3 days'"
  - Next message routed through TeacherAgent.handle_assignment_instruction

/status handler (teachers only):
  - Calls SummariserAgent.generate_teacher_digest
  - Sends formatted digest

/mystatus handler (students only):
  - Shows student's active assignments with status, deadline, latest progress

/link handler (students only):
  - Prompts student for invite code
  - Validates code and links to teacher

CALLBACK QUERY HANDLER (for inline buttons):
  Handle: "role_teacher", "role_student", "confirm_submit_{assignment_id}", "cancel_submit"

MESSAGE HANDLER (the core routing hub):
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    This is the central message router. For every text message:
    1. Get user from DB by telegram_id (create if /start was just pressed)
    2. Get user's conversation state from ConversationState table
    3. If state == "awaiting_feedback": route to TeacherAgent.handle_feedback
    4. If state == "awaiting_submission": collect and route to StudentAgent.handle_submission
    5. Otherwise: call IntentAgent.classify, then route to appropriate agent method
    6. Send all response messages
    7. Update conversation state if state_transition is set
    """

DOCUMENT/PHOTO HANDLER:
async def handle_document(update, context):
    """Handle file submissions from students — route to StudentAgent.handle_submission with file_id"""

async def handle_photo(update, context):
    """Handle photo submissions — get largest photo size, route to StudentAgent.handle_submission"""

async def handle_voice(update, context):
    """Handle voice notes — get file_id, route to StudentAgent.handle_voice_submission"""

REGISTRATION FLOW:
async def handle_teacher_registration(update, context):
    """
    1. Create User record with role="teacher"
    2. Generate unique invite_code (8-char alphanumeric)
    3. Send: "Welcome, {name}! Your invite code is: {code}. Share this with your students."
    """

async def handle_student_registration(update, context):
    """
    1. Prompt for invite code
    2. Validate code → find teacher
    3. Create TeacherStudentLink
    4. Send: "You're now linked to {teacher_name}! You'll receive assignments here."
    5. Notify teacher: "{student_name} just joined your classroom!"
    """

APPLICATION FACTORY:
def create_application(settings: Settings) -> Application:
    """
    Build the Application with all handlers registered.
    Order of handlers matters — more specific first.
    """

--- bot/middleware.py ---
Create a middleware class that:
1. Logs every incoming update (telegram_id, message type, text snippet)
2. Rate-limits: max 30 messages per user per minute (use simple in-memory dict)
3. Checks if user is banned/inactive before processing
4. Provides get_or_create_user(telegram_id, full_name) helper that:
   - Checks DB for existing user
   - If not found, creates with role=None and state="idle"
   - Returns User model instance
```

---

## ═══════════════════════════════════════════════
## SECTION 6 — FASTAPI BACKEND & ROUTES
## ═══════════════════════════════════════════════

```
@workspace Generate api/main.py and all routes under api/routes/.

--- api/main.py ---
Create the FastAPI application:
- Mount /static for serving Teacher and Student web UIs
- Include all routers with prefixes
- Lifespan handler: initialize DB on startup
- CORS: allow all origins in debug mode
- Exception handlers for 404 and 500

--- api/routes/health.py ---
GET /health → returns {"status": "ok", "timestamp": ..., "db": "connected"|"error"}

--- api/routes/teacher.py ---
All endpoints require teacher_id as query param (simplified auth for interview).
No production auth needed — just validate that the user exists and has role="teacher".

GET /api/teacher/{teacher_id}/dashboard
Response:
{
  "teacher": {name, telegram_handle, invite_code},
  "students": [
    {
      "id": ...,
      "name": ...,
      "telegram_handle": ...,
      "assignments": [
        {
          "id": ...,
          "title": ...,
          "description": ...,
          "due_date": ...,
          "status": ...,
          "days_remaining": ...,
          "latest_progress": ...,   // last ProgressUpdate message or null
          "submitted_at": ...,      // null if not submitted
          "has_feedback": bool
        }
      ]
    }
  ]
}

GET /api/teacher/{teacher_id}/assignments
Query params: status (optional filter), student_id (optional filter)
Returns list of all assignments with full details

GET /api/teacher/{teacher_id}/student/{student_id}/summary
Returns LLM-generated summary for that student (calls SummariserAgent)

POST /api/teacher/{teacher_id}/assignment
Body: { student_id, title, description, due_date }
Creates assignment directly from UI (bonus: inline UI action)

--- api/routes/student.py ---
All endpoints require student_id as query param.

GET /api/student/{student_id}/dashboard
Response:
{
  "student": {name, telegram_handle},
  "teacher": {name, telegram_handle},
  "assignments": [
    {
      "id": ...,
      "title": ...,
      "description": ...,
      "due_date": ...,
      "status": ...,
      "days_remaining": ...,
      "progress_updates": [...],
      "submission": { text_content, file_type, submitted_at } | null,
      "feedback": { formatted_feedback, created_at } | null
    }
  ]
}

GET /api/student/{student_id}/assignments/{assignment_id}
Returns full detail for a single assignment including all progress, submission, feedback.
```

---

## ═══════════════════════════════════════════════
## SECTION 7 — SCHEDULER SETUP
## ═══════════════════════════════════════════════

```
@workspace Generate scheduler/reminder_scheduler.py.

Use APScheduler 3.x with AsyncIOScheduler.

class ReminderScheduler:
    def __init__(self, bot, settings: Settings, db_factory):
        self.scheduler = AsyncIOScheduler(timezone="UTC")
        self.bot = bot
        self.settings = settings
        self.db_factory = db_factory
    
    def start(self):
        """
        Schedule these jobs:
        
        1. "check_reminders" — CronTrigger at 9:00 AM UTC daily
           Calls ReminderAgent.process_due_reminders with reminder_type="daily"
        
        2. "check_escalations" — CronTrigger at 6:00 PM UTC daily
           Calls ReminderAgent.process_due_reminders with reminder_type="escalation"
           Only fires for assignments with days_remaining <= 2
        
        3. "final_warning" — CronTrigger at 8:00 AM UTC daily
           Calls ReminderAgent.process_due_reminders with reminder_type="final_warning"
           Only fires for assignments due today (days_remaining == 0)
        
        4. "overdue_check" — IntervalTrigger every 6 hours
           Finds assignments that are past due and not submitted
           Notifies teacher once via _send_overdue_teacher_notification
        
        5. "teacher_digest" — CronTrigger every Monday at 8:00 AM UTC
           Sends weekly digest to all teachers via SummariserAgent.generate_teacher_digest
        """
        self.scheduler.start()
    
    def stop(self):
        self.scheduler.shutdown(wait=False)

    async def _run_reminder_job(self, reminder_type: str):
        async with self.db_factory() as db:
            agent = ReminderAgent(llm=get_llm_provider(), db=db)
            await agent.process_due_reminders(self.bot, reminder_type=reminder_type)
```

---

## ═══════════════════════════════════════════════
## SECTION 8 — MAIN ENTRY POINT
## ═══════════════════════════════════════════════

```
@workspace Generate main.py — the unified entry point that starts everything together.

"""
main.py — starts the Telegram bot + FastAPI server + APScheduler in a single process.

Architecture:
- FastAPI runs on uvicorn (async)
- Telegram bot uses webhook mode (production) or polling mode (local dev flag)
- APScheduler runs on the same asyncio event loop
- All components share the same SQLite DB connection pool

Startup sequence:
1. Load settings from .env
2. Initialize DB (create tables)
3. Optionally seed test data (if SEED_DB=true in env)
4. Create LLM provider singleton
5. Create Telegram Application
6. Set up ngrok tunnel (if LOCAL_DEV=true) → get public URL → set webhook
7. Start APScheduler
8. Start uvicorn with FastAPI app
9. Graceful shutdown on SIGINT/SIGTERM

Implement:
async def setup_ngrok(settings) -> str:
    Use pyngrok or subprocess to start ngrok tunnel on port settings.app_port
    Return the https public URL
    Print: "🌐 ngrok tunnel: {url}"

async def set_telegram_webhook(application, webhook_url):
    await application.bot.set_webhook(url=f"{webhook_url}/webhook")
    Print: "📡 Webhook set: {webhook_url}/webhook"

async def main():
    Full startup as described above.
    Include try/finally for graceful shutdown.

if __name__ == "__main__":
    asyncio.run(main())
"""
```

---

## ═══════════════════════════════════════════════
## SECTION 9 — TEACHER WEB UI
## ═══════════════════════════════════════════════

```
@workspace Generate static/teacher/index.html, static/teacher/style.css, static/teacher/app.js.

DESIGN DIRECTION: Professional, clean, editorial. Dark navy (#0F172A) background with cream 
(#F8F4EF) content areas. Use "DM Serif Display" for headings, "DM Sans" for body. 
Green (#10B981) for submitted, amber (#F59E0B) for in_progress, red (#EF4444) for overdue.
No frameworks — vanilla JS fetching from /api/teacher/{id}/ endpoints.

TEACHER UI FEATURES:
1. Login/Entry section: Simple input to enter teacher_id (e.g. 100001 for Prof. Sharma)
   Show teacher name + invite code prominently once loaded

2. Students Panel: 
   - Grid of student cards, each showing:
     - Student name + @handle
     - Assignment count + status breakdown (chips: X submitted, Y in progress, Z pending)
     - "View Details" button that expands/shows assignment list
   
3. Assignment Table (expanded per student):
   - Columns: Title | Due Date | Days Left | Status | Latest Progress | Actions
   - Status badge with color coding
   - "Ask AI" button next to each student: opens a modal where teacher types 
     "How is {name} doing?" and gets LLM summary (calls /api/teacher/{id}/student/{sid}/summary)
   - Inline feedback prompt if status == "submitted" and no feedback exists yet

4. Summary Panel:
   - "📊 Generate Full Digest" button → calls API and renders teacher digest in a modal

5. Auto-refresh every 30 seconds (with a subtle "Last updated X seconds ago" indicator)

6. Responsive design: works on desktop and tablet

Make it visually impressive — this is a demo piece. Use CSS Grid, smooth transitions, 
and thoughtful micro-interactions. Every state (loading, empty, error) must be handled.

URL scheme: /teacher (served by FastAPI static mount)
Teacher ID is stored in localStorage after first entry.
```

---

## ═══════════════════════════════════════════════
## SECTION 10 — STUDENT WEB UI
## ═══════════════════════════════════════════════

```
@workspace Generate static/student/index.html, static/student/style.css, static/student/app.js.

DESIGN DIRECTION: Warm, motivating, slightly playful. Light mode with warm white (#FFFBF5) 
background. Soft purple (#7C3AED) as primary accent. Use "Fraunces" for headings (expressive 
serif), "Plus Jakarta Sans" for body. Celebrate completion with a confetti burst effect (CSS only).
Status colors: purple=in_progress, green=submitted/reviewed, orange=nearly_due, red=overdue.

STUDENT UI FEATURES:
1. Login/Entry: Input for student_id (e.g. 200001 for Riya Singh)
   Show student name + teacher name once loaded

2. Assignment Cards (the main view):
   Each assignment card shows:
   - Title (large, prominent)
   - Description (truncated with expand toggle)
   - Due date + countdown ("3 days left" / "Due TODAY" / "Overdue by 1 day")
   - Status badge with icon (📝 Pending, 🔄 In Progress, ✅ Submitted, 🌟 Reviewed)
   - Progress timeline: ordered list of all progress updates with timestamps
   - Submission details if submitted (file type icon + submitted_at)
   - Feedback section: if feedback exists, show in a highlighted "Teacher says:" card
     with a warm yellow (#FEF3C7) background

3. Countdown Timer: For the most urgent assignment, show a live countdown in HH:MM:SS

4. Empty state: Friendly message "No assignments yet! Your teacher will assign work soon. 🎉"

5. Celebration state: When an assignment status is "reviewed", show a subtle 
   sparkle/star animation on that card

6. Auto-refresh every 60 seconds

Make this feel like a delightful companion app, not a boring dashboard.
URL scheme: /student (served by FastAPI static mount)
Student ID stored in localStorage.
```

---

## ═══════════════════════════════════════════════
## SECTION 11 — TESTS: UNIT TESTS
## ═══════════════════════════════════════════════

```
@workspace Generate all unit test files. Every agent must have full coverage. 
Use pytest-asyncio, unittest.mock for LLM calls, and pytest fixtures.

--- tests/conftest.py ---
Define pytest fixtures:
- event_loop: session-scoped async event loop
- test_db: creates a fresh SQLite test DB, seeds it, yields AsyncSession, drops all after
- mock_llm: MagicMock that returns controlled responses for each tool
- sample_teacher: User fixture for a teacher
- sample_student: User fixture for a student
- sample_assignment: Assignment fixture linked to above teacher/student

--- tests/fixtures/test_data.py ---
Define all test constants and factory functions:
- TEACHER_1_ID = 100001
- STUDENT_1_ID = 200001
- etc. (matching seed.py)
- make_assignment(teacher_id, student_id, days_until_due, status) factory
- make_progress_update(assignment_id, student_id, message, status) factory

--- tests/unit/test_intent_agent.py ---
Test IntentAgent.classify for ALL intents:
- test_classify_assign_work: message="Assign Riya a 500-word essay" → intent="assign_work"
- test_classify_progress_update: message="done 2 paragraphs" → intent="progress_update"
- test_classify_completion: message="I've finished the essay" → intent="submission"
- test_classify_teacher_query: message="how is Riya doing?" → intent="teacher_query"
- test_classify_register_teacher: message="/start" with "I'm a Teacher" → intent="register_teacher"
- test_classify_unknown: message="pizza is great" → intent="unknown"
- test_classify_with_low_confidence: verify fallback behavior when confidence < 0.5
Mock the LLM response for each test case.

--- tests/unit/test_teacher_agent.py ---
- test_handle_assignment_instruction_success: 
  Mock LLM parse_assignment_instruction response, verify DB record created, 
  verify notify_student action returned with correct telegram_id
- test_handle_assignment_unknown_student:
  Student name not in teacher's linked students → should return helpful error message
- test_handle_feedback_success:
  Mock LLM generate_feedback_message, verify Feedback record created, 
  assignment status updated to "reviewed", notify_student returned
- test_handle_student_query:
  Mock LLM answer_teacher_query, verify answer returned
- test_handle_summary_request:
  Multiple students with assignments → verify digest contains all student names

--- tests/unit/test_student_agent.py ---
- test_handle_progress_update_in_progress:
  message="done 2 paragraphs" → verify ProgressUpdate created with in_progress
- test_handle_progress_update_completed_routes_to_submission:
  message="all done!" → verify flow redirects to submission handling
- test_handle_submission_text_only:
  No file → verify Submission created with text_content only
- test_handle_submission_with_file:
  file_id="abc", file_type="document" → verify Submission created with file_id
- test_handle_voice_submission:
  voice file → verify transcript captured, submission created
- test_submission_notifies_teacher:
  Verify notify action is returned with teacher's telegram_id
- test_submission_sets_teacher_state_to_awaiting_feedback:
  Verify ConversationState for teacher is updated

--- tests/unit/test_reminder_agent.py ---
Use freezegun to control datetime.
- test_should_send_daily_reminder:
  Assignment due in 5 days, no recent reminder → should_send=True, type="daily"
- test_should_not_send_if_recently_reminded:
  Assignment with reminder sent 3 hours ago → should_send=False
- test_should_escalate_when_due_in_2_days:
  Assignment due in 2 days → type="escalation"
- test_final_warning_due_today:
  Assignment due today → type="final_warning"
- test_skip_reminder_for_submitted_assignment:
  Assignment status="submitted" → should_send=False
- test_skip_reminder_if_nearly_done_and_daily:
  Student status="nearly_done" → skip daily, send motivational nudge

--- tests/unit/test_summariser_agent.py ---
- test_generate_student_summary_in_progress
- test_generate_student_summary_overdue
- test_generate_teacher_digest_multiple_students
- test_answer_student_query_for_teacher
All mock LLM responses.
```

---

## ═══════════════════════════════════════════════
## SECTION 12 — TESTS: INTEGRATION TESTS
## ═══════════════════════════════════════════════

```
@workspace Generate integration test files. These tests run against the seeded test DB 
and test the FastAPI endpoints + end-to-end agent flows.

--- tests/integration/test_api_teacher.py ---
Use httpx AsyncClient with FastAPI test app, seeded DB.

Tests:
- test_get_teacher_dashboard_prof_sharma:
  GET /api/teacher/100001/dashboard
  Assert: 2 students (Riya, Arjun), correct assignment counts, statuses match seed data

- test_get_teacher_dashboard_students_have_assignments:
  Verify Riya has 1 assignment, status="in_progress"
  Verify Arjun has 1 assignment, status="pending", days_remaining=1 (escalation candidate)

- test_get_teacher_assignments_filter_by_status:
  GET /api/teacher/100001/assignments?status=pending
  Assert: returns only pending assignments

- test_get_teacher_assignments_filter_by_student:
  GET /api/teacher/100001/assignments?student_id=200001
  Assert: returns only Riya's assignments

- test_get_student_summary:
  GET /api/teacher/100001/student/200001/summary
  Mock LLM, assert summary contains student name

- test_teacher_not_found_returns_404:
  GET /api/teacher/999999/dashboard → 404

- test_wrong_role_returns_403:
  GET /api/teacher/200001/dashboard (student ID used as teacher) → 403

--- tests/integration/test_api_student.py ---
- test_get_student_dashboard_riya:
  GET /api/student/200001/dashboard
  Assert: assignment "Photosynthesis essay" present, status="in_progress"
  Assert: 1 progress update present ("done 2 paragraphs...")

- test_get_student_dashboard_priya_submitted:
  GET /api/student/200003/dashboard
  Assert: assignment status="submitted", submission present

- test_get_student_dashboard_karan_reviewed:
  GET /api/student/200004/dashboard
  Assert: assignment has feedback with formatted_feedback text

- test_student_assignment_detail:
  GET /api/student/200001/assignments/{assignment_id}
  Assert: full detail including progress_updates list

- test_student_not_found_returns_404

--- tests/integration/test_bot_flows.py ---
Test the full end-to-end message flows using mock Telegram Updates.
Use AsyncMock for bot.send_message.

Helper: make_telegram_update(telegram_id, text, role) → creates a fake Update object

Tests:

- test_full_assign_flow:
  1. Simulate teacher (100001) sending: "Assign Riya a 500-word essay on photosynthesis, due in 3 days"
  2. Mock IntentAgent → "assign_work"
  3. Mock TeacherAgent.handle_assignment_instruction → AgentResponse(action="notify_student", ...)
  4. Assert bot.send_message called twice: once to student (assignment), once to teacher (confirm)
  5. Assert Assignment created in DB

- test_full_progress_flow:
  1. Simulate student (200001) sending: "I've done 3 paragraphs now"
  2. Mock intent → "progress_update"  
  3. Assert ProgressUpdate created in DB
  4. Assert teacher notified

- test_full_submission_flow:
  1. Student sends: "I'm done! Here is my essay." with text
  2. Assert Assignment status → "submitted"
  3. Assert teacher notified with submission
  4. Assert teacher ConversationState → "awaiting_feedback"

- test_full_feedback_flow:
  1. Teacher (in awaiting_feedback state) sends: "Good work but needs more analysis"
  2. Assert Feedback created in DB
  3. Assert Assignment status → "reviewed"
  4. Assert student receives formatted feedback

- test_teacher_query_flow:
  1. Teacher sends: "how is Riya doing this week?"
  2. Mock intent → "teacher_query"
  3. Mock summariser → answer text
  4. Assert teacher receives LLM-generated answer

- test_reminder_flow:
  1. Call ReminderAgent.process_due_reminders directly (no Telegram needed)
  2. Mock APScheduler trigger
  3. Assert Arjun (1 day remaining) gets escalation reminder
  4. Assert Riya (3 days remaining) gets daily reminder
  5. Assert Priya (submitted) gets NO reminder
```

---

## ═══════════════════════════════════════════════
## SECTION 13 — README & ARCHITECTURE DOCS
## ═══════════════════════════════════════════════

```
@workspace Generate README.md — comprehensive, interview-quality documentation.

The README must include ALL of the following sections with full content (no placeholders):

# 🎓 Classroom Companion — AI-Powered Assignment Management Bot

## Table of Contents
1. Overview
2. Architecture
3. Agent Design & Prompt Strategy
4. Tech Stack
5. Setup & Installation
6. Running Locally (ngrok)
7. Running Tests
8. API Reference
9. Web UI Guide
10. End-to-End Flow Diagrams
11. Known Limitations & Trade-offs
12. What I'd Build Next
13. AI Collaboration Notes

---

## 2. Architecture
Include an ASCII architecture diagram showing:
- Telegram ↔ Bot Handlers ↔ Intent Agent → [Teacher Agent | Student Agent]
- APScheduler → Reminder Agent
- All agents → SQLite DB
- FastAPI → Static UIs
- LLM Provider (Grok) called by all agents

Example ASCII:
┌─────────────────────────────────────────────────────────────────┐
│                    CLASSROOM COMPANION                          │
├─────────────────────────────────────────────────────────────────┤
│  Telegram App                                                   │
│     │ Updates                                                   │
│     ▼                                                           │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  python-telegram-bot v20 (Webhook/Polling)               │  │
│  │  bot/handlers.py — routes by message type                │  │
│  └─────────────────────────┬────────────────────────────────┘  │
│                            │                                    │
│                            ▼                                    │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │             AGENT ORCHESTRATION LAYER                   │   │
│  │  ┌────────────┐   ┌──────────────┐  ┌───────────────┐  │   │
│  │  │ IntentAgent│──▶│ TeacherAgent │  │ StudentAgent  │  │   │
│  │  └────────────┘   └──────────────┘  └───────────────┘  │   │
│  │       │           ┌──────────────┐  ┌───────────────┐  │   │
│  │  ┌────────────┐   │ReminderAgent │  │SummariserAgent│  │   │
│  │  │LLM Provider│   └──────────────┘  └───────────────┘  │   │
│  │  │  (Grok)    │                                         │   │
│  │  └────────────┘                                         │   │
│  └─────────────────────────────────────────────────────────┘   │
│                            │                                    │
│             ┌──────────────┼──────────────┐                    │
│             ▼              ▼              ▼                    │
│  ┌──────────────┐  ┌──────────────┐ ┌──────────────┐          │
│  │  SQLite DB   │  │  FastAPI     │ │ APScheduler  │          │
│  │  (aiosqlite) │  │  REST API    │ │  (AsyncIO)   │          │
│  └──────────────┘  └──────┬───────┘ └──────────────┘          │
│                           │                                     │
│                    ┌──────┴───────┐                            │
│                    │  Static UIs  │                            │
│                    │Teacher|Std't │                            │
│                    └──────────────┘                            │
└─────────────────────────────────────────────────────────────────┘

## 3. Agent Design & Prompt Strategy
For each agent, document:
- Purpose
- System prompt (full text)
- Tools used
- Input → Output contract
- Failure/fallback handling

## 5. Setup & Installation
Exact steps:
1. Clone repo
2. python -m venv .venv && source .venv/bin/activate (or Windows equivalent)
3. pip install -r requirements.txt
4. cp .env.example .env → fill in TELEGRAM_BOT_TOKEN, GROK_API_KEY, NGROK_AUTH_TOKEN
5. python -m database.seed (seeds test data)
6. python main.py (starts everything)

## 6. Running Locally
ngrok setup:
1. Download ngrok from ngrok.com
2. ngrok config add-authtoken YOUR_TOKEN
3. main.py auto-starts ngrok tunnel and sets webhook

## 7. Running Tests
pytest tests/ -v --cov=. --cov-report=html
pytest tests/unit/ -v           # unit tests only
pytest tests/integration/ -v    # integration tests only

## 10. End-to-End Flow Diagrams
Include ASCII sequence diagrams for ALL these flows:

FLOW 1: Teacher Assigns Work
Teacher → Telegram → IntentAgent (assign_work) → TeacherAgent 
→ parse_assignment_instruction (Grok) → DB create Assignment 
→ generate_assignment_message (Grok) → Telegram → Student

FLOW 2: Student Reports Progress
Student → Telegram → IntentAgent (progress_update) → StudentAgent
→ classify_student_message (Grok) → DB create ProgressUpdate
→ generate_status_summary (Grok) → Telegram → Teacher

FLOW 3: Student Submits (with file)
Student sends file → bot/handlers handle_document → StudentAgent.handle_submission
→ DB create Submission → Teacher notified → Teacher state = awaiting_feedback

FLOW 4: Teacher Gives Feedback
Teacher (awaiting_feedback state) → ConversationState check → TeacherAgent.handle_feedback
→ generate_feedback_message (Grok) → DB create Feedback → Student notified

FLOW 5: Reminder Fire
APScheduler tick → ReminderAgent.process_due_reminders
→ DB query non-submitted assignments → _should_send_reminder logic
→ generate_reminder_message (Grok) → Telegram → Student
→ DB log Reminder record

FLOW 6: Teacher Query
Teacher: "How is Riya doing?" → IntentAgent (teacher_query) → TeacherAgent.handle_student_query
→ DB fetch all assignments + progress → answer_teacher_query (Grok) → Telegram → Teacher

## 11. Known Limitations & Trade-offs
Be honest — include:
- SQLite concurrency limits (would use Postgres in production)
- No real auth (invite codes only)
- Voice transcription stubbed (Whisper integration noted)
- Single-process deployment (would separate services in production)
- No message deduplication for Telegram webhook retries

## 12. What I'd Build Next (≤300 words)
- Production auth (JWT or Telegram's OAuth)
- Switch to Postgres + connection pooling
- Separate Reminder service (Celery + Redis)
- Real voice transcription with Whisper API
- Assignment file storage (S3/GCS instead of Telegram file IDs)
- WebSocket live updates for Teacher/Student UIs
- Multi-teacher per student support
- LangGraph for formal agent graph with state persistence

## 13. AI Collaboration Notes
Document exactly how AI tools were used:
- Which prompts were given to Copilot
- What was accepted vs rejected
- What the LLM got wrong on first attempt and how you corrected it
- How you validated LLM-generated code before committing
```

---

## ═══════════════════════════════════════════════
## SECTION 14 — FINAL WIRING & RUN COMMANDS
## ═══════════════════════════════════════════════

```
@workspace Final step: wire everything together and provide the complete run script.

1. Verify main.py correctly imports and starts:
   - FastAPI app (uvicorn)
   - Telegram Application (webhook via ngrok)
   - APScheduler
   - DB initialization
   - Optional seeding (SEED_DB=true)

2. Add a Makefile with these targets:
   make install     — pip install -r requirements.txt
   make seed        — python -m database.seed
   make run         — python main.py
   make test        — pytest tests/ -v --cov=. --cov-report=html
   make test-unit   — pytest tests/unit/ -v
   make test-int    — pytest tests/integration/ -v
   make clean       — remove *.db, __pycache__, .coverage

3. Add scripts/run_demo.sh:
   #!/bin/bash
   # One-command demo setup
   echo "🎓 Starting Classroom Companion..."
   python -m database.seed
   echo "✅ Test data seeded"
   echo "Teacher 1 (Prof. Sharma) ID: 100001"
   echo "Teacher 2 (Dr. Patel) ID: 100002"
   echo "Student IDs: 200001, 200002, 200003, 200004"
   echo "Teacher UI: http://localhost:8000/teacher"
   echo "Student UI: http://localhost:8000/student"
   python main.py

4. Create pytest.ini:
   [pytest]
   asyncio_mode = auto
   testpaths = tests
   python_files = test_*.py
   python_classes = Test*
   python_functions = test_*
   addopts = -v --tb=short

5. Final check — ensure these work without error:
   python -c "from config import get_settings; print(get_settings())"
   python -c "from database.models import Base; print('Models OK')"
   python -c "from llm.provider import get_llm_provider; print('LLM OK')"
   python -c "from agents.intent_agent import IntentAgent; print('Agents OK')"
   python -c "from api.main import app; print('FastAPI OK')"
```

---

## ═══════════════════════════════════════════════
## QUICK REFERENCE — INTERVIEW DEMO FLOW
## ═══════════════════════════════════════════════

```
DEMO SCRIPT FOR INTERVIEW (save this):

Setup before interview:
1. Have Telegram open on phone + screen share
2. Have Teacher UI (localhost:8000/teacher?id=100001) open in browser tab 2
3. Have Student UI (localhost:8000/student?id=200001) open in browser tab 3

Demo sequence (10 minutes):

Step 1 — Show Teacher UI:
  Open browser → Teacher dashboard → Prof. Sharma's students (Riya, Arjun)
  Point out: Arjun is due in 1 day (escalation zone), Riya is in_progress

Step 2 — Assign work (live on Telegram):
  From Teacher bot: "Assign Riya a 300-word paragraph on Newton's laws, due in 2 days"
  Show Teacher UI auto-refresh → new assignment appears

Step 3 — Student receives assignment:
  Switch to Student Telegram account (Riya)
  Show assignment message received with deadline

Step 4 — Student progress:
  Student sends: "I've written the intro part"
  Show teacher gets notified in Telegram
  Show Student UI: progress update appears

Step 5 — Student submits:
  Student sends: "Completed! Here is my work: Newton's first law states..."
  Show teacher receives submission + feedback prompt

Step 6 — Teacher feedback:
  Teacher sends: "Great job! But add more examples"
  Show student receives formatted encouraging feedback

Step 7 — Teacher query:
  Teacher: "How has Arjun been doing this week?"
  Show LLM-generated summary response

Step 8 — Show Student UI (Riya):
  Assignment history, feedback visible, timeline of progress

Live code challenge hints:
- To swap LLM: change .env LLM_PROVIDER=openai → restart → same behavior
- To add new agent: create agents/new_agent.py extending BaseAgent → register in handlers.py
- To change reminder policy: edit reminder_agent.py _should_send_reminder logic
```

---

*End of Master Copilot Prompt — Classroom Companion*
*SIM Engineering Interview Assignment — Full Implementation Guide*
*Version 1.0 — All 14 sections must be completed in order*
