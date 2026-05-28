from functools import lru_cache
from typing import Optional

from openai import AsyncOpenAI
from openai.types.chat import ChatCompletion

from config import Settings, get_settings


class LLMProvider:
    """
    Provider-agnostic LLM wrapper.
    Switch providers by changing the LLM_PROVIDER env var:
      grok    → xAI Grok via OpenAI-compatible endpoint
      openai  → OpenAI (GPT-4o, etc.)
      gemini  → Google Gemini via OpenAI-compatible endpoint

    Zero code changes needed — only the .env value changes.
    """

    def __init__(self, settings: Settings):
        self.settings = settings
        self.client: AsyncOpenAI = self._build_client()
        self.model: str = settings.llm_model

    def _build_client(self) -> AsyncOpenAI:
        """Return an AsyncOpenAI client configured for the selected provider."""
        provider = self.settings.llm_provider.lower()

        if provider == "grok":
            return AsyncOpenAI(
                api_key=self.settings.grok_api_key,
                base_url="https://api.x.ai/v1",
            )
        elif provider == "openai":
            return AsyncOpenAI(
                api_key=self.settings.openai_api_key,
            )
        elif provider == "gemini":
            return AsyncOpenAI(
                api_key=self.settings.gemini_api_key,
                base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
            )
        else:
            raise ValueError(
                f"Unknown LLM provider: '{provider}'. "
                "Supported values: grok, openai, gemini"
            )

    async def complete(
        self,
        system_prompt: str,
        user_message: str,
        tools: Optional[list[dict]] = None,
        tool_choice: str = "auto",
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> ChatCompletion:
        """
        Core single-turn completion used by all agents.

        Args:
            system_prompt: The agent's persona / instruction prompt.
            user_message:  The user's message to process.
            tools:         Optional list of OpenAI-format tool schemas.
            tool_choice:   "auto" | "none" | {"type": "function", "function": {"name": "..."}}
            temperature:   Overrides settings default when provided.
            max_tokens:    Overrides settings default when provided.

        Returns:
            ChatCompletion from the OpenAI SDK.
        """
        kwargs: dict = {
            "model": self.model,
            "temperature": temperature if temperature is not None else self.settings.llm_temperature,
            "max_tokens": max_tokens if max_tokens is not None else self.settings.llm_max_tokens,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
        }
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = tool_choice

        return await self.client.chat.completions.create(**kwargs)

    async def complete_with_history(
        self,
        system_prompt: str,
        messages: list[dict],
        tools: Optional[list[dict]] = None,
        tool_choice: str = "auto",
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> ChatCompletion:
        """
        Multi-turn completion that accepts a full message history.

        Args:
            system_prompt: The agent's persona / instruction prompt.
            messages:      List of {"role": ..., "content": ...} dicts (no system msg).
            tools:         Optional tool schemas.
            tool_choice:   Tool selection strategy.

        Returns:
            ChatCompletion from the OpenAI SDK.
        """
        full_messages = [{"role": "system", "content": system_prompt}] + messages

        kwargs: dict = {
            "model": self.model,
            "temperature": temperature if temperature is not None else self.settings.llm_temperature,
            "max_tokens": max_tokens if max_tokens is not None else self.settings.llm_max_tokens,
            "messages": full_messages,
        }
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = tool_choice

        return await self.client.chat.completions.create(**kwargs)

    def extract_text(self, response: ChatCompletion) -> str:
        """Extract plain text content from a completion response."""
        choice = response.choices[0]
        if choice.message.content:
            return choice.message.content.strip()
        return ""

    def extract_tool_call(self, response: ChatCompletion) -> Optional[tuple[str, dict]]:
        """
        Extract the first tool call from a completion response.

        Returns:
            (tool_name, arguments_dict) or None if no tool call was made.
        """
        choice = response.choices[0]
        if choice.message.tool_calls:
            tool_call = choice.message.tool_calls[0]
            import json
            args = json.loads(tool_call.function.arguments)
            return tool_call.function.name, args
        return None


_llm_provider_instance: Optional[LLMProvider] = None


def get_llm_provider(settings: Optional[Settings] = None) -> LLMProvider:
    """
    Cached singleton factory for LLMProvider.
    Pass settings explicitly in tests to inject mocks.
    """
    global _llm_provider_instance
    if _llm_provider_instance is None:
        _llm_provider_instance = LLMProvider(settings or get_settings())
    return _llm_provider_instance


def reset_llm_provider() -> None:
    """Reset the singleton (used in tests to swap providers)."""
    global _llm_provider_instance
    _llm_provider_instance = None
