from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from llm.provider import LLMProvider


@dataclass
class AgentResponse:
    """Standardised response returned by every agent handle() call."""

    message: str
    action: str  # "reply" | "no_reply" | "notify_teacher" | "notify_student"
    notify_telegram_id: Optional[int] = None
    notification_message: Optional[str] = None
    notification_file_id: Optional[str] = None
    notification_file_type: Optional[str] = None
    notification_file_name: Optional[str] = None
    notification_caption: Optional[str] = None
    state_transition: Optional[str] = None  # new conversation state for the sender
    metadata: dict = field(default_factory=dict)


class BaseAgent(ABC):
    """Abstract base class for all Classroom Companion agents."""

    def __init__(self, llm: LLMProvider, db: AsyncSession):
        self.llm = llm
        self.db = db
        self.logger = logger.bind(agent=self.__class__.__name__)

    @abstractmethod
    async def handle(self, telegram_id: int, message: str, **kwargs) -> AgentResponse:
        """Entry point for processing a user message. Must be implemented by subclasses."""
        ...

    def _ok(
        self,
        message: str,
        action: str = "reply",
        notify_telegram_id: Optional[int] = None,
        notification_message: Optional[str] = None,
        notification_file_id: Optional[str] = None,
        notification_file_type: Optional[str] = None,
        notification_file_name: Optional[str] = None,
        notification_caption: Optional[str] = None,
        state_transition: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> AgentResponse:
        """Convenience builder for a successful AgentResponse."""
        return AgentResponse(
            message=message,
            action=action,
            notify_telegram_id=notify_telegram_id,
            notification_message=notification_message,
            notification_file_id=notification_file_id,
            notification_file_type=notification_file_type,
            notification_file_name=notification_file_name,
            notification_caption=notification_caption,
            state_transition=state_transition,
            metadata=metadata or {},
        )

    def _error(self, message: str) -> AgentResponse:
        """Convenience builder for an error AgentResponse."""
        return AgentResponse(message=message, action="reply")
