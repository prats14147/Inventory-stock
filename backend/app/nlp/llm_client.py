"""
backend/app/nlp/llm_client.py

Thin wrapper around the Groq API (OpenAI-compatible). Kept behind a small
interface (`complete_json`, `complete_text`) so the rest of the NLP layer
never depends on the Groq SDK directly -- this is what lets
chat_service.py be tested with a FakeLLMClient (see backend/tests/) even
in environments without network access to api.groq.com.
"""

from __future__ import annotations

from app.config import get_settings


class LLMUnavailableError(Exception):
    """Raised when the LLM call fails for any reason (network, auth, rate limit, etc.)."""


class GroqClient:
    """Real client -- used in production. Requires GROQ_API_KEY to be set."""

    def __init__(self, api_key: str | None = None, model: str | None = None):
        settings = get_settings()
        self.api_key = api_key or settings.groq_api_key
        self.model = model or settings.groq_model
        self._client = None

    def _get_client(self):
        if self._client is None:
            if not self.api_key:
                raise LLMUnavailableError("GROQ_API_KEY is not set.")
            try:
                from groq import Groq
            except ImportError as e:
                raise LLMUnavailableError(f"groq package not installed: {e}") from e
            self._client = Groq(api_key=self.api_key)
        return self._client

    def complete_json(self, system_prompt: str, user_message: str) -> str:
        try:
            client = self._get_client()
            response = client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message},
                ],
                response_format={"type": "json_object"},
                temperature=0.0,
            )
            return response.choices[0].message.content
        except Exception as e:  # noqa: BLE001 -- any failure here should degrade gracefully upstream
            raise LLMUnavailableError(str(e)) from e

    def complete_text(self, system_prompt: str, user_message: str) -> str:
        try:
            client = self._get_client()
            response = client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message},
                ],
                temperature=0.3,
            )
            return response.choices[0].message.content
        except Exception as e:  # noqa: BLE001
            raise LLMUnavailableError(str(e)) from e

    def stream_text(self, system_prompt: str, user_message: str):
        """Yield the phrased response in chunks (real token streaming).

        Same prompt/contract as `complete_text`, but lazy, so the caller can
        forward each chunk to a live client (see app/routers/ws.py). Raises
        LLMUnavailableError on any failure -- callers fall back to the
        deterministic template formatter, exactly like the non-streaming path.
        """
        try:
            client = self._get_client()
            stream = client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message},
                ],
                temperature=0.3,
                stream=True,
            )
            for chunk in stream:
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta.content
                if delta:
                    yield delta
        except Exception as e:  # noqa: BLE001
            raise LLMUnavailableError(str(e)) from e
