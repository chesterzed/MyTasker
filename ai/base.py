"""
ai/base.py

Provider-agnostic interface for talking to an LLM. Concrete providers
(ai/claude_client.py, ai/ollama_client.py, ...) subclass BaseAIClient.
"""
from __future__ import annotations

import abc
from dataclasses import dataclass
from typing import Literal

Role = Literal["user", "assistant"]


@dataclass(frozen=True)
class ChatMessage:
    role: Role
    content: str


class AIClientError(Exception):
    """Base exception for all AI client errors. Callers should catch this
    (or a more specific subclass) around every send_message call."""


class AIAuthError(AIClientError):
    """The configured API key is invalid, revoked, or unauthorized."""


class AIRateLimitError(AIClientError):
    """The provider rate-limited the request."""


class AITimeoutError(AIClientError):
    """The request timed out or the provider is unreachable."""


class AIResponseError(AIClientError):
    """Any other non-2xx or malformed-response error from the provider."""


class BaseAIClient(abc.ABC):
    """Provider-agnostic interface for sending a conversation to an LLM and
    getting a text response back."""

    def __init__(self, api_key: str, default_model: str, timeout: float = 60.0) -> None:
        self.api_key = api_key
        self.default_model = default_model
        self.timeout = timeout

    @abc.abstractmethod
    async def send_message(
        self,
        messages: list[ChatMessage],
        *,
        system_prompt: str | None = None,
        model: str | None = None,
        max_tokens: int = 1024,
        temperature: float | None = None,
    ) -> str:
        """Send a full conversation (built by the caller from messages_log
        rows) and return the assistant's reply as plain text.

        Raises:
            AIAuthError, AIRateLimitError, AITimeoutError, AIResponseError
        """
        raise NotImplementedError
