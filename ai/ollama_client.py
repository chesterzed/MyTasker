"""
ai/ollama_client.py

Client for a local Ollama server.
"""
from __future__ import annotations

import ollama

from ai.base import AIClientError, AIResponseError, AITimeoutError, BaseAIClient, ChatMessage

DEFAULT_OLLAMA_HOST = "http://localhost:11434"


class OllamaClient(BaseAIClient):
    """Client for a local Ollama server. No API key is required - api_key is
    accepted only for constructor symmetry with BaseAIClient / KeyManager."""

    def __init__(
        self,
        default_model: str,
        api_key: str | None = None,
        host: str = DEFAULT_OLLAMA_HOST,
        timeout: float = 120.0,
    ) -> None:
        # default_model has no sensible universal default (unlike Claude) - it
        # must be a model already pulled locally (e.g. "llama3.1").
        super().__init__(api_key=api_key or "", default_model=default_model, timeout=timeout)
        self._client = ollama.AsyncClient(host=host, timeout=timeout)

    async def send_message(
        self,
        messages: list[ChatMessage],
        *,
        system_prompt: str | None = None,
        model: str | None = None,
        max_tokens: int = 1024,
        temperature: float | None = None,
    ) -> str:
        api_messages: list[dict] = []
        if system_prompt:
            api_messages.append({"role": "system", "content": system_prompt})
        api_messages.extend({"role": m.role, "content": m.content} for m in messages)

        options: dict = {"num_predict": max_tokens}
        if temperature is not None:
            options["temperature"] = temperature

        try:
            response = await self._client.chat(
                model=model or self.default_model,
                messages=api_messages,
                options=options,
                stream=False,
            )
        except ollama.ResponseError as exc:
            raise AIResponseError(str(exc)) from exc
        except (TimeoutError, ConnectionError) as exc:
            raise AITimeoutError(str(exc)) from exc
        except Exception as exc:  # underlying httpx transport errors, etc.
            raise AIClientError(str(exc)) from exc

        return response["message"]["content"]
