"""
ai/claude_client.py

Stateless ("incognito") client for the Anthropic Messages API.
"""
from __future__ import annotations

import anthropic

from ai.base import (
    AIAuthError,
    AIClientError,
    AIRateLimitError,
    AIResponseError,
    AITimeoutError,
    BaseAIClient,
    ChatMessage,
)

DEFAULT_CLAUDE_MODEL = "claude-opus-4-8"


class ClaudeClient(BaseAIClient):
    """Stateless ("incognito") client for the Anthropic Messages API.

    Stateless here means each call sends the full relevant message history
    explicitly (built by the caller from messages_log); Anthropic keeps no
    server-side conversation/session state between calls.
    """

    def __init__(
        self,
        api_key: str,
        default_model: str = DEFAULT_CLAUDE_MODEL,
        timeout: float = 60.0,
    ) -> None:
        super().__init__(api_key=api_key, default_model=default_model, timeout=timeout)
        self._client = anthropic.AsyncAnthropic(api_key=api_key, timeout=timeout)

    async def send_message(
        self,
        messages: list[ChatMessage],
        *,
        system_prompt: str | None = None,
        model: str | None = None,
        max_tokens: int = 1024,
        temperature: float | None = None,
    ) -> str:
        api_messages = [{"role": m.role, "content": m.content} for m in messages]

        kwargs: dict = {
            "model": model or self.default_model,
            "max_tokens": max_tokens,
            "messages": api_messages,
        }
        if system_prompt:
            kwargs["system"] = system_prompt
        if temperature is not None:
            # NOTE: claude-opus-4-8 (and other current-generation models) reject
            # `temperature` with a 400 error. Only pass this if the target model
            # is known to support it.
            kwargs["temperature"] = temperature

        try:
            response = await self._client.messages.create(**kwargs)
        except anthropic.AuthenticationError as exc:
            raise AIAuthError(str(exc)) from exc
        except anthropic.RateLimitError as exc:
            raise AIRateLimitError(str(exc)) from exc
        except anthropic.APITimeoutError as exc:
            raise AITimeoutError(str(exc)) from exc
        except anthropic.APIStatusError as exc:
            raise AIResponseError(str(exc)) from exc
        except anthropic.APIConnectionError as exc:
            raise AIResponseError(str(exc)) from exc

        if response.stop_reason == "refusal":
            raise AIResponseError("Claude declined to respond (safety refusal).")

        return "".join(block.text for block in response.content if block.type == "text")
