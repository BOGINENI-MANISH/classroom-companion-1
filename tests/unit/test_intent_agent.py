"""Unit tests for IntentAgent."""
import json
from unittest.mock import MagicMock

import pytest

from agents.intent_agent import IntentAgent, IntentResult

INTENTS = [
    "register_teacher",
    "register_student",
    "assign_work",
    "progress_update",
    "submission",
    "feedback",
    "teacher_query",
    "request_summary",
    "help",
    "unknown",
]


def _mock_llm_for_intent(intent: str, confidence: float = 0.9) -> MagicMock:
    """Build a mock LLM that returns the given intent as JSON text."""
    from unittest.mock import AsyncMock
    llm = MagicMock()
    payload = json.dumps({"intent": intent, "confidence": confidence, "reasoning": "test reason"})
    llm.complete = AsyncMock(return_value=MagicMock())
    llm.extract_text = MagicMock(return_value=payload)
    return llm


@pytest.mark.asyncio
async def test_classify_returns_intent_result(db):
    """classify() returns an IntentResult with all fields populated."""
    llm = _mock_llm_for_intent("progress_update", confidence=0.95)
    agent = IntentAgent(llm=llm, db=db)
    result = await agent.classify(telegram_id=1, message="I finished chapter 1")
    assert isinstance(result, IntentResult)
    assert result.intent == "progress_update"
    assert result.confidence == pytest.approx(0.95)
    assert result.reasoning == "test reason"


@pytest.mark.asyncio
async def test_classify_low_confidence_returns_unknown(db):
    """When confidence < 0.4, the agent should fall back to 'unknown'."""
    llm = _mock_llm_for_intent("assign_work", confidence=0.2)
    agent = IntentAgent(llm=llm, db=db)
    result = await agent.classify(telegram_id=1, message="blah blah blah")
    assert result.intent == "unknown"


@pytest.mark.asyncio
@pytest.mark.parametrize("intent", INTENTS)
async def test_all_intent_labels_parseable(db, intent):
    """All 10 known intents are parsed correctly from LLM output."""
    llm = _mock_llm_for_intent(intent, confidence=0.85)
    agent = IntentAgent(llm=llm, db=db)
    result = await agent.classify(telegram_id=99, message="test")
    assert result.intent == intent


@pytest.mark.asyncio
async def test_classify_handles_malformed_json(db):
    """If LLM returns malformed JSON, classify() falls back to 'unknown'."""
    from unittest.mock import AsyncMock
    llm = MagicMock()
    llm.complete = AsyncMock(return_value=MagicMock())
    llm.extract_text = MagicMock(return_value="NOT JSON AT ALL")
    agent = IntentAgent(llm=llm, db=db)
    result = await agent.classify(telegram_id=1, message="garbage")
    assert result.intent == "unknown"
    assert result.confidence == 0.0


@pytest.mark.asyncio
async def test_classify_strips_markdown_fences(db):
    """classify() correctly strips ```json ... ``` fences from LLM output."""
    from unittest.mock import AsyncMock
    llm = MagicMock()
    payload = '```json\n{"intent":"submission","confidence":0.91,"reasoning":"done"}\n```'
    llm.complete = AsyncMock(return_value=MagicMock())
    llm.extract_text = MagicMock(return_value=payload)
    agent = IntentAgent(llm=llm, db=db)
    result = await agent.classify(telegram_id=1, message="I'm done with everything")
    assert result.intent == "submission"


@pytest.mark.asyncio
async def test_handle_wraps_classify(db):
    """handle() returns an AgentResponse containing the intent in metadata."""
    llm = _mock_llm_for_intent("teacher_query", confidence=0.88)
    agent = IntentAgent(llm=llm, db=db)
    response = await agent.handle(telegram_id=100, message="How is Riya doing?", role="teacher")
    assert response.action == "reply"
    assert "intent_result" in response.metadata
    assert response.metadata["intent_result"].intent == "teacher_query"
