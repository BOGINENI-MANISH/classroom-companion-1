import json
from dataclasses import dataclass
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from agents.base_agent import AgentResponse, BaseAgent
from llm.provider import LLMProvider

INTENT_SYSTEM_PROMPT = """
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
Do not include any other text, markdown, or explanation outside the JSON object.
""".strip()


@dataclass
class IntentResult:
    intent: str
    confidence: float
    reasoning: str


class IntentAgent(BaseAgent):
    """Classifies the intent of any incoming message regardless of user role."""

    def __init__(self, llm: LLMProvider, db: AsyncSession):
        super().__init__(llm, db)

    async def handle(self, telegram_id: int, message: str, **kwargs) -> AgentResponse:
        """Thin wrapper — callers should use classify() directly."""
        result = await self.classify(telegram_id, message, role=kwargs.get("role", "unknown"))
        return self._ok(result.intent, metadata={"intent_result": result})

    async def classify(
        self, telegram_id: int, message: str, role: str = "unknown"
    ) -> IntentResult:
        """
        Classify the intent of a message.

        Args:
            telegram_id: Sender's Telegram ID (for logging).
            message:     Raw text of the message.
            role:        Caller's known role ("teacher" | "student" | "unknown").

        Returns:
            IntentResult with intent, confidence, and reasoning.
        """
        user_msg = f"Role: {role}\nMessage: {message}"

        try:
            response = await self.llm.complete(
                system_prompt=INTENT_SYSTEM_PROMPT,
                user_message=user_msg,
                temperature=0.1,  # low temp for deterministic classification
                max_tokens=200,
            )
            raw = self.llm.extract_text(response)

            # Strip markdown code fences if present
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
                raw = raw.strip()

            parsed = json.loads(raw)
            intent = parsed.get("intent", "unknown")
            confidence = float(parsed.get("confidence", 0.0))
            reasoning = parsed.get("reasoning", "")

            # Fall back to unknown if confidence is too low
            if confidence < 0.4:
                self.logger.warning(
                    f"Low confidence ({confidence:.2f}) for intent '{intent}' "
                    f"from telegram_id={telegram_id}. Falling back to 'unknown'."
                )
                intent = "unknown"

            self.logger.info(
                f"Intent classified: telegram_id={telegram_id} "
                f"intent={intent} confidence={confidence:.2f}"
            )
            return IntentResult(intent=intent, confidence=confidence, reasoning=reasoning)

        except (json.JSONDecodeError, KeyError, ValueError) as exc:
            self.logger.error(f"Intent parse error for telegram_id={telegram_id}: {exc}")
            return IntentResult(intent="unknown", confidence=0.0, reasoning=str(exc))
        except Exception as exc:
            self.logger.error(f"Intent LLM error for telegram_id={telegram_id}: {exc}")
            return IntentResult(intent="unknown", confidence=0.0, reasoning=str(exc))
