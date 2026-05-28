# Classroom Companion

An AI-powered assignment management system for teachers and students, delivered through a Telegram bot and a companion web dashboard.

---

## Table of Contents

1. [Overview](#overview)
2. [Architecture](#architecture)
3. [Agent Design](#agent-design)
4. [Project Structure](#project-structure)
5. [Setup & Installation](#setup--installation)
6. [Configuration Reference](#configuration-reference)
7. [Running the App](#running-the-app)
8. [API Reference](#api-reference)
9. [Testing](#testing)
10. [Database Schema](#database-schema)

---

## Overview

Classroom Companion lets a teacher manage student assignments entirely through natural-language messages in a Telegram chat.  Students receive assignments, submit updates, and get AI-generated feedback — all inside Telegram.  Web dashboards (separate for teachers and students) provide a visual overview backed by the same REST API.

**Key capabilities**

| Feature | How it works |
|---|---|
| Natural-language assignment instructions | Teacher types a message; `IntentAgent` classifies it, `TeacherAgent` parses and persists the assignment |
| Student progress tracking | Students send free-text updates; `StudentAgent` interprets status and stores a `ProgressUpdate` record |
| Automated reminders | `APScheduler` runs five cron/interval jobs; `ReminderAgent` decides type and generates personalised reminder text via LLM |
| AI-generated summaries | `SummariserAgent` answers teacher queries about individual students and produces weekly class digests |
| Multi-provider LLM | Pluggable backend supporting Grok (default), OpenAI, and Gemini via a unified `LLMProvider` interface |

---

## Architecture

```
                          ┌──────────────────────────────────────────┐
                          │             TELEGRAM CLIENTS              │
                          │   Teacher chat          Student chat      │
                          └──────────┬──────────────────┬────────────┘
                                     │  Webhook (HTTPS)  │
                        ┌────────────▼──────────────────▼────────────┐
                        │              FASTAPI APPLICATION            │
                        │                                             │
                        │  ┌─────────────────────────────────────┐  │
                        │  │         python-telegram-bot          │  │
                        │  │  ┌────────────┐  ┌───────────────┐  │  │
                        │  │  │ Middleware  │  │   Handlers    │  │  │
                        │  │  │(auth/state)│  │ (teacher/     │  │  │
                        │  │  └────────────┘  │  student)     │  │  │
                        │  │                  └───────┬───────┘  │  │
                        │  └──────────────────────────│──────────┘  │
                        │                             │              │
                        │  ┌──────────────────────────▼──────────┐  │
                        │  │              AGENT LAYER             │  │
                        │  │                                      │  │
                        │  │  ┌──────────┐    ┌───────────────┐  │  │
                        │  │  │  Intent  │    │    Teacher    │  │  │
                        │  │  │  Agent   │───▶│    Agent      │  │  │
                        │  │  └──────────┘    └───────────────┘  │  │
                        │  │                                      │  │
                        │  │  ┌──────────┐    ┌───────────────┐  │  │
                        │  │  │ Student  │    │   Reminder    │  │  │
                        │  │  │  Agent   │    │    Agent      │  │  │
                        │  │  └──────────┘    └───────────────┘  │  │
                        │  │                                      │  │
                        │  │  ┌──────────────────────────────┐   │  │
                        │  │  │       Summariser Agent       │   │  │
                        │  │  └──────────────────────────────┘   │  │
                        │  └──────────────────────┬──────────────┘  │
                        │                         │                  │
                        │  ┌──────────────────────▼──────────────┐  │
                        │  │           LLM PROVIDER               │  │
                        │  │  Grok / OpenAI / Gemini (pluggable)  │  │
                        │  └──────────────────────────────────────┘  │
                        │                                             │
                        │  ┌──────────────────────────────────────┐  │
                        │  │         APSCHEDULER (async)          │  │
                        │  │  daily · escalation · final_warning  │  │
                        │  │  overdue_check · teacher_digest      │  │
                        │  └──────────────────────────────────────┘  │
                        │                                             │
                        │  ┌──────────────────────────────────────┐  │
                        │  │        REST API ROUTES               │  │
                        │  │  /api/teacher/*   /api/student/*     │  │
                        │  │  /health                             │  │
                        │  └──────────────────────────────────────┘  │
                        └─────────────────────┬───────────────────────┘
                                              │
                        ┌─────────────────────▼───────────────────────┐
                        │           SQLite (aiosqlite + SQLAlchemy 2)  │
                        │  users · assignments · progress_updates      │
                        │  submissions · feedback · reminders          │
                        │  teacher_student_links · conversation_states │
                        └──────────────────────────────────────────────┘

                        ┌──────────────────────────────────────────────┐
                        │              WEB DASHBOARDS (static)         │
                        │   /static/teacher/   ←→   /static/student/  │
                        │         Vanilla JS + REST API calls          │
                        └──────────────────────────────────────────────┘
```

All components run in a **single process on a single asyncio event loop** — FastAPI (uvicorn), python-telegram-bot, and APScheduler share the loop, eliminating inter-process communication overhead.

---

## Agent Design

Every agent inherits from `BaseAgent` and receives a shared `LLMProvider` and an async `AsyncSession`.

### IntentAgent

Classifies every incoming message into one of ten intents using a structured LLM prompt that returns JSON:

```
assign_task · progress_update · submission · feedback_request
query_student · query_assignment · reminder_request · cancel_task
general_chat · unknown
```

Returns an `IntentResult(intent, confidence, reasoning)` dataclass. Low-confidence results (`< 0.6`) are coerced to `unknown`.

### TeacherAgent

Handles teacher-side Telegram messages after intent classification.

- `handle_assignment_instruction(teacher_telegram_id, message)` — parses the instruction via LLM tool call, resolves the named student from the teacher's roster (exact match then first-name fallback), persists an `Assignment` record, and notifies the student.
- `handle_feedback(teacher_telegram_id, message, assignment_id)` — generates formatted feedback for a submission via LLM and persists a `Feedback` record.

### StudentAgent

Handles student-side Telegram messages.

- `handle_progress_update(student_telegram_id, message)` — verifies registration, finds the active assignment, stores a `ProgressUpdate`, and returns an encouraging reply.
- `handle_submission(student_telegram_id, message, file_id, file_type, file_name)` — marks the assignment `submitted`, creates a `Submission` record, and notifies the teacher.
- `handle_message(student_telegram_id, message, ...)` — dispatch router: routes to `handle_submission` if `file_id` is present, otherwise `handle_progress_update`.

### ReminderAgent

Core method: `_should_send_reminder(assignment, last_reminder, reminder_type) → (bool, str)`.

Decision rules (evaluated in order):

| Condition | Result |
|---|---|
| `assignment.status == "submitted"` | Skip |
| `last_reminder` sent within `MIN_REMINDER_GAP_HOURS` | Skip |
| `days_remaining < 0` and no `overdue_teacher` reminder yet | Send `overdue_teacher` |
| `days_remaining < 0` and already notified | Skip |
| Latest progress is `nearly_done` | Send `motivational_nudge` |
| `days_remaining == 0` | Send `final_warning` |
| `days_remaining <= 2` | Send `escalation` |
| Otherwise | Send `daily` |

### SummariserAgent

- `generate_student_summary(student_id, assignment_id)` — produces a concise progress summary from stored `ProgressUpdate` records via LLM tool call.
- `answer_student_query_for_teacher(teacher_telegram_id, student_name, query)` — answers an ad-hoc teacher question about a named student.
- `generate_teacher_digest(teacher_telegram_id)` — builds a weekly class overview across all students.

---

## Project Structure

```
classroom-companion-1/
├── agents/
│   ├── base_agent.py          # AgentResponse dataclass + BaseAgent ABC
│   ├── intent_agent.py        # IntentAgent — message classification
│   ├── teacher_agent.py       # TeacherAgent — assignment & feedback flow
│   ├── student_agent.py       # StudentAgent — progress & submission flow
│   ├── reminder_agent.py      # ReminderAgent — reminder logic & scheduling
│   └── summariser_agent.py    # SummariserAgent — LLM summaries & digests
│
├── api/
│   ├── main.py                # FastAPI app factory (create_app)
│   └── routes/
│       ├── health.py          # GET /health
│       ├── teacher.py         # /api/teacher/* (dashboard, assignments, summary, create)
│       └── student.py         # /api/student/* (dashboard, assignments, detail)
│
├── bot/
│   ├── handlers.py            # Telegram message/command handlers
│   └── middleware.py          # Auth, rate-limiting, conversation-state middleware
│
├── database/
│   ├── models.py              # SQLAlchemy 2.0 ORM models (mapped_column style)
│   ├── database.py            # Engine + session factory + get_db dependency
│   └── seed.py                # Demo data seeding
│
├── llm/
│   ├── provider.py            # LLMProvider — unified OpenAI-compatible client
│   └── tools.py               # Tool/function definitions for structured LLM output
│
├── scheduler/
│   └── reminder_scheduler.py  # ReminderScheduler — APScheduler job registration
│
├── static/
│   ├── teacher/               # Teacher web dashboard (HTML + CSS + JS)
│   └── student/               # Student web dashboard (HTML + CSS + JS)
│
├── tests/
│   ├── conftest.py            # Shared fixtures: in-memory DB, seed users/assignments
│   ├── fixtures/
│   │   └── test_data.py       # Factory helpers: make_user, make_assignment, …
│   ├── unit/                  # Pure-logic unit tests (48 tests)
│   │   ├── test_intent_agent.py
│   │   ├── test_teacher_agent.py
│   │   ├── test_student_agent.py
│   │   ├── test_summariser_agent.py
│   │   └── test_reminder_agent.py
│   └── integration/           # HTTP integration tests via httpx.AsyncClient (22 tests)
│       ├── conftest.py        # App fixture with get_db override
│       ├── test_api_teacher.py
│       └── test_api_student.py
│
├── main.py                    # Application entry point (uvicorn + bot + scheduler)
├── config.py                  # pydantic-settings Settings class
├── requirements.txt
├── .env.example
└── .gitignore
```

---

## Setup & Installation

### Prerequisites

- Python 3.11+
- A Telegram bot token from [@BotFather](https://t.me/BotFather)
- An API key for at least one LLM provider (Grok / OpenAI / Gemini)
- (Optional) An ngrok auth token for local webhook development

### 1 — Clone and create a virtual environment

```bash
git clone <repo-url>
cd classroom-companion-1
python -m venv .venv

# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate
```

### 2 — Install dependencies

```bash
pip install -r requirements.txt
```

### 3 — Configure environment variables

```bash
cp .env.example .env
```

Edit `.env` with your real values (see [Configuration Reference](#configuration-reference)).

### 4 — (Optional) Seed demo data

```bash
python -c "
import asyncio
from database.database import init_db
from database.seed import seed_demo_data
asyncio.run(init_db())
asyncio.run(seed_demo_data())
"
```

Or set `SEED_DB=true` in `.env` to seed automatically on first startup.

### 5 — Run

```bash
python main.py
```

---

## Configuration Reference

All settings are read from `.env` via `pydantic-settings`.

| Variable | Default | Description |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | *(required)* | Bot token from @BotFather |
| `NGROK_AUTH_TOKEN` | *(optional)* | ngrok auth token for local webhook tunnelling |
| `WEBHOOK_BASE_URL` | *(optional)* | Override the auto-detected ngrok URL |
| `LLM_PROVIDER` | `grok` | One of `grok`, `openai`, `gemini` |
| `GROK_API_KEY` | *(optional)* | API key for Grok (xAI) |
| `OPENAI_API_KEY` | *(optional)* | API key for OpenAI |
| `GEMINI_API_KEY` | *(optional)* | API key for Gemini |
| `LLM_MODEL` | `grok-3` | Model name passed to the provider |
| `LLM_TEMPERATURE` | `0.3` | Sampling temperature |
| `LLM_MAX_TOKENS` | `1024` | Max tokens per LLM response |
| `DATABASE_URL` | `sqlite+aiosqlite:///./classroom_companion.db` | Async SQLAlchemy URL |
| `APP_HOST` | `0.0.0.0` | uvicorn bind host |
| `APP_PORT` | `8000` | uvicorn bind port |
| `DEBUG` | `true` | Enables `/docs`, `/redoc`, and SQLAlchemy echo |
| `LOG_LEVEL` | `INFO` | loguru log level |
| `REMINDER_CHECK_INTERVAL_MINUTES` | `60` | How often the overdue check job runs |
| `REMINDER_DAILY_HOUR` | `9` | Hour (UTC) for the daily reminder cron job |
| `REMINDER_DAILY_MINUTE` | `0` | Minute for the daily reminder cron job |
| `ESCALATION_DAYS_BEFORE_DEADLINE` | `2` | Days remaining that trigger escalation reminders |
| `LOCAL_DEV` | `true` | Enables ngrok tunnel; set `false` in production |
| `SEED_DB` | `false` | Seed demo data on startup |

---

## Running the App

### Development (ngrok webhook)

```bash
# Ensure LOCAL_DEV=true and NGROK_AUTH_TOKEN is set in .env
python main.py
```

The app will:
1. Start an ngrok tunnel on port 8000
2. Register the Telegram webhook at `https://<ngrok-url>/telegram/webhook`
3. Serve the API and static dashboards

### Production (fixed webhook URL)

```bash
# Set in .env:
#   LOCAL_DEV=false
#   WEBHOOK_BASE_URL=https://your-production-domain.com
python main.py
```

### Polling mode (no webhook)

If no `WEBHOOK_BASE_URL` is available and `LOCAL_DEV=false`, the bot automatically falls back to long-polling.

### Web dashboards

| Dashboard | URL |
|---|---|
| Teacher | `http://localhost:8000/static/teacher/` |
| Student | `http://localhost:8000/static/student/` |
| API docs | `http://localhost:8000/docs` (only when `DEBUG=true`) |
| Health check | `http://localhost:8000/health` |

---

## API Reference

### Health

```
GET /health
```

Returns `{"status": "ok", "database": "connected", "timestamp": "..."}`.  Returns `status: "degraded"` if the DB is unreachable.

---

### Teacher API

All routes are prefixed `/api/teacher`.

#### Get dashboard summary

```
GET /api/teacher/{teacher_id}/dashboard
```

Returns assignment counts by status and linked student count.

**Response** `200`
```json
{
  "teacher": { "id": 1, "telegram_id": 123456, "full_name": "Alice", "telegram_handle": "alice" },
  "total_students": 3,
  "assignments_pending": 1,
  "assignments_in_progress": 2,
  "assignments_submitted": 1,
  "assignments_reviewed": 0
}
```

---

#### List assignments

```
GET /api/teacher/{teacher_id}/assignments?status=in_progress&student_id=2
```

Both query parameters are optional.

**Response** `200` — array of assignment objects with `student_name` attached.

---

#### Get student summary

```
GET /api/teacher/{teacher_id}/student/{student_id}/summary
```

Returns an AI-generated progress summary for each of the student's assignments.

**Response** `200`
```json
{
  "student_id": 2,
  "student_name": "Bob",
  "assignments": [
    { "assignment_id": 5, "title": "Essay", "summary": "Bob has completed the outline..." }
  ]
}
```

---

#### Create assignment

```
POST /api/teacher/{teacher_id}/assignment
Content-Type: application/json

{
  "student_telegram_id": 200001,
  "title": "Research Essay",
  "description": "Write 500 words on climate change.",
  "due_date": "2026-06-15T23:59:00Z"
}
```

**Response** `201` — the created assignment object.  
Returns `403` if the student is not linked to the teacher, `404` if teacher or student not found.

---

### Student API

All routes are prefixed `/api/student`.

#### Get dashboard summary

```
GET /api/student/{student_id}/dashboard
```

**Response** `200`
```json
{
  "student_id": 2,
  "student_name": "Bob",
  "total_assignments": 3,
  "pending": 0,
  "in_progress": 2,
  "submitted": 1,
  "reviewed": 0
}
```

---

#### List assignments

```
GET /api/student/{student_id}/assignments
```

Returns full assignment details including progress updates, submission, feedback, and an AI summary.

---

#### Get assignment detail

```
GET /api/student/{student_id}/assignments/{assignment_id}
```

Returns a single assignment's full detail view.

---

## Testing

The project has **70 tests** across two suites, both using an in-memory SQLite database.

```bash
# All tests
python -m pytest tests/ -v --asyncio-mode=auto

# Unit tests only (48 tests)
python -m pytest tests/unit/ -v --asyncio-mode=auto

# Integration tests only (22 tests)
python -m pytest tests/integration/ -v --asyncio-mode=auto

# With coverage
python -m pytest tests/ --cov=. --cov-report=term-missing --asyncio-mode=auto
```

### Test design

**Unit tests** (`tests/unit/`) mock the LLM and database at the agent boundary.  
`ReminderAgent` tests use `types.SimpleNamespace` objects instead of ORM instances to avoid SQLAlchemy greenlet constraints.

**Integration tests** (`tests/integration/`) spin up the real FastAPI app using `httpx.AsyncClient` with `ASGITransport`, override the `get_db` dependency with the test session, and patch `get_llm_provider` where LLM calls would occur.

---

## Database Schema

```
users
  id · telegram_id · telegram_handle · full_name · role · invite_code
  created_at · is_active

teacher_student_links
  id · teacher_id → users.id · student_id → users.id · linked_at

assignments
  id · teacher_id → users.id · student_id → users.id
  title · description · raw_instruction · due_date · status
  created_at · updated_at

progress_updates
  id · assignment_id → assignments.id · student_id → users.id
  message · interpreted_status · created_at

submissions
  id · assignment_id → assignments.id · student_id → users.id
  text_content · file_id · file_type · file_name · submitted_at

feedback
  id · assignment_id → assignments.id · teacher_id → users.id
  raw_feedback · formatted_feedback · created_at

reminders
  id · assignment_id → assignments.id · student_id → users.id
  reminder_type · message · sent_at

conversation_states
  id · telegram_id (unique) · state · context_json · updated_at
```

`assignment.status` lifecycle: `pending` → `in_progress` → `submitted` → `reviewed`
