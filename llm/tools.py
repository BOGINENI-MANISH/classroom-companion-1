"""
All OpenAI-format function-calling tool schemas used by the agent layer.

Each tool is defined as a dict following the OpenAI Chat Completions tools spec:
  {
      "type": "function",
      "function": {
          "name": str,
          "description": str,
          "parameters": { "type": "object", "properties": {...}, "required": [...] }
      }
  }

The ToolRegistry class provides convenient lookup by name.
"""

from typing import Any


# ── Tool Definitions ─────────────────────────────────────────────────────────

PARSE_ASSIGNMENT_INSTRUCTION: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "parse_assignment_instruction",
        "description": (
            "Parse a teacher's natural language assignment instruction into structured fields. "
            "Extract the student name, assignment title, full description, and deadline."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "student_name": {
                    "type": "string",
                    "description": "Full or first name of the student being assigned work.",
                },
                "title": {
                    "type": "string",
                    "description": "Brief assignment title, maximum 60 characters.",
                },
                "description": {
                    "type": "string",
                    "description": "Full, clear assignment description with all relevant details.",
                },
                "due_days": {
                    "type": "integer",
                    "description": "Number of days from today until the assignment is due (1–30).",
                    "minimum": 1,
                    "maximum": 30,
                },
                "word_count": {
                    "type": ["integer", "null"],
                    "description": "Required word or page count if explicitly mentioned, else null.",
                },
            },
            "required": ["student_name", "title", "description", "due_days"],
        },
    },
}

CLASSIFY_STUDENT_MESSAGE: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "classify_student_message",
        "description": (
            "Classify a student's incoming message intent and extract structured information "
            "about their progress or submission."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "intent": {
                    "type": "string",
                    "enum": [
                        "progress_update",
                        "completion",
                        "question",
                        "submission_text",
                        "other",
                    ],
                    "description": "The primary intent of the student's message.",
                },
                "progress_description": {
                    "type": "string",
                    "description": "Brief summary of what the student has done so far.",
                },
                "completion_confirmed": {
                    "type": "boolean",
                    "description": "True if the student explicitly states they have finished.",
                },
                "has_attachment": {
                    "type": "boolean",
                    "description": "True if the message mentions or implies a file or photo.",
                },
                "interpreted_status": {
                    "type": "string",
                    "enum": ["not_started", "in_progress", "nearly_done", "completed"],
                    "description": "LLM-interpreted progress status based on the message content.",
                },
            },
            "required": [
                "intent",
                "progress_description",
                "completion_confirmed",
                "has_attachment",
                "interpreted_status",
            ],
        },
    },
}

GENERATE_ASSIGNMENT_MESSAGE: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "generate_assignment_message",
        "description": (
            "Generate a friendly, motivating assignment notification message to send to a student."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "student_name": {
                    "type": "string",
                    "description": "The student's first name.",
                },
                "assignment_title": {
                    "type": "string",
                    "description": "Title of the assignment.",
                },
                "assignment_description": {
                    "type": "string",
                    "description": "Full assignment description.",
                },
                "due_date_str": {
                    "type": "string",
                    "description": "Human-readable due date string, e.g. 'Friday, 31 May 2026'.",
                },
                "tone": {
                    "type": "string",
                    "enum": ["warm", "encouraging", "urgent"],
                    "description": "Desired tone of the message.",
                },
                "generated_message": {
                    "type": "string",
                    "description": "The complete message to send to the student.",
                },
            },
            "required": [
                "student_name",
                "assignment_title",
                "assignment_description",
                "due_date_str",
                "tone",
                "generated_message",
            ],
        },
    },
}

GENERATE_REMINDER_MESSAGE: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "generate_reminder_message",
        "description": (
            "Generate an intelligent, personalised reminder message for a student about "
            "an upcoming assignment deadline. Vary tone based on urgency and reminder number."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "student_name": {
                    "type": "string",
                    "description": "The student's first name.",
                },
                "assignment_title": {
                    "type": "string",
                    "description": "Title of the assignment.",
                },
                "due_date_str": {
                    "type": "string",
                    "description": "Human-readable due date string.",
                },
                "days_remaining": {
                    "type": "integer",
                    "description": "Number of days remaining until the deadline.",
                },
                "last_progress": {
                    "type": ["string", "null"],
                    "description": "The student's most recent progress update, or null if none.",
                },
                "reminder_number": {
                    "type": "integer",
                    "description": "Which reminder this is (1st, 2nd, 3rd, etc.) to vary wording.",
                },
                "generated_message": {
                    "type": "string",
                    "description": "The complete reminder message to send to the student.",
                },
            },
            "required": [
                "student_name",
                "assignment_title",
                "due_date_str",
                "days_remaining",
                "reminder_number",
                "generated_message",
            ],
        },
    },
}

GENERATE_FEEDBACK_MESSAGE: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "generate_feedback_message",
        "description": (
            "Convert a teacher's raw, concise feedback into a friendly, constructive, "
            "and motivating message suitable for sending directly to the student."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "student_name": {
                    "type": "string",
                    "description": "The student's first name.",
                },
                "assignment_title": {
                    "type": "string",
                    "description": "Title of the assignment being reviewed.",
                },
                "raw_teacher_feedback": {
                    "type": "string",
                    "description": "The teacher's original, unformatted feedback text.",
                },
                "formatted_message": {
                    "type": "string",
                    "description": (
                        "The polished, encouraging feedback message to send to the student. "
                        "Should acknowledge effort, highlight strengths, and frame improvements positively."
                    ),
                },
            },
            "required": [
                "student_name",
                "assignment_title",
                "raw_teacher_feedback",
                "formatted_message",
            ],
        },
    },
}

GENERATE_STATUS_SUMMARY: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "generate_status_summary",
        "description": (
            "Generate a concise status summary of a student's assignment progress for the teacher."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "student_name": {
                    "type": "string",
                    "description": "The student's full name.",
                },
                "assignment_title": {
                    "type": "string",
                    "description": "Title of the assignment.",
                },
                "status": {
                    "type": "string",
                    "description": "Current assignment status (pending, in_progress, submitted, reviewed).",
                },
                "progress_updates": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of the student's progress update messages in chronological order.",
                },
                "due_date_str": {
                    "type": "string",
                    "description": "Human-readable due date string.",
                },
                "summary_text": {
                    "type": "string",
                    "description": "The generated 2–3 line status summary for the teacher.",
                },
            },
            "required": [
                "student_name",
                "assignment_title",
                "status",
                "progress_updates",
                "due_date_str",
                "summary_text",
            ],
        },
    },
}

ANSWER_TEACHER_QUERY: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "answer_teacher_query",
        "description": (
            "Answer a teacher's specific question about a student using the available "
            "assignment and progress context. Synthesise the information into a clear, "
            "actionable response."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The teacher's original question.",
                },
                "student_name": {
                    "type": "string",
                    "description": "The student's full name.",
                },
                "assignments_context": {
                    "type": "string",
                    "description": (
                        "JSON string summarising the student's assignments, statuses, "
                        "progress updates, and submissions."
                    ),
                },
                "answer": {
                    "type": "string",
                    "description": "The complete, helpful answer to the teacher's query.",
                },
            },
            "required": ["query", "student_name", "assignments_context", "answer"],
        },
    },
}


# ── Tool Registry ─────────────────────────────────────────────────────────────

_ALL_TOOLS: dict[str, dict] = {
    "parse_assignment_instruction": PARSE_ASSIGNMENT_INSTRUCTION,
    "classify_student_message": CLASSIFY_STUDENT_MESSAGE,
    "generate_assignment_message": GENERATE_ASSIGNMENT_MESSAGE,
    "generate_reminder_message": GENERATE_REMINDER_MESSAGE,
    "generate_feedback_message": GENERATE_FEEDBACK_MESSAGE,
    "generate_status_summary": GENERATE_STATUS_SUMMARY,
    "answer_teacher_query": ANSWER_TEACHER_QUERY,
}


class ToolRegistry:
    """Central registry for all OpenAI-format tool schemas."""

    def get_tools(self, names: list[str]) -> list[dict]:
        """Return tool schemas for the given list of tool names."""
        result = []
        for name in names:
            if name not in _ALL_TOOLS:
                raise KeyError(f"Tool '{name}' not found in registry.")
            result.append(_ALL_TOOLS[name])
        return result

    def get_all_tools(self) -> list[dict]:
        """Return all registered tool schemas."""
        return list(_ALL_TOOLS.values())

    def get_tool_names(self) -> list[str]:
        """Return all registered tool names."""
        return list(_ALL_TOOLS.keys())


# Singleton instance
tool_registry = ToolRegistry()
