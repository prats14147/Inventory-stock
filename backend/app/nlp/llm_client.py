"""
backend/app/nlp/llm_client.py

Thin wrapper around the Groq API (OpenAI-compatible). Kept behind a small
interface (`complete_json`, `complete_text`) so the rest of the NLP layer
never depends on the Groq SDK directly -- this is what lets
chat_service.py be tested with a FakeLLMClient (see backend/tests/) even
in environments without network access to api.groq.com.
"""

from __future__ import annotations

import json
import logging
import time

import httpx

from app.config import get_settings

log = logging.getLogger("nlp.llm_client")


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


class GeminiClient:
    """Gemini REST client implementing the same narrow interface as GroqClient.

    Uses Google's documented generateContent / streamGenerateContent endpoints
    over the already-installed httpx dependency, so the project does not need
    a second provider SDK just to switch models.
    """

    API_ROOT = "https://generativelanguage.googleapis.com/v1beta/models"

    def __init__(self, api_key: str | None = None, model: str | None = None):
        settings = get_settings()
        self.api_key = api_key or settings.gemini_api_key or settings.groq_api_key
        self.model = model or settings.gemini_model
        self.fallback_model = settings.gemini_fallback_model

    def _request_body(self, system_prompt: str, user_message: str, *, json_mode: bool = False) -> dict:
        generation_config = {"temperature": 0.0 if json_mode else 0.2}
        if json_mode:
            generation_config["responseMimeType"] = "application/json"
        return {
            "systemInstruction": {"parts": [{"text": system_prompt}]},
            "contents": [{"role": "user", "parts": [{"text": user_message}]}],
            "generationConfig": generation_config,
        }

    def _url(self, streaming: bool = False, model: str | None = None) -> str:
        model = (model or self.model).removeprefix("models/")
        method = "streamGenerateContent?alt=sse" if streaming else "generateContent"
        return f"{self.API_ROOT}/{model}:{method}"

    @staticmethod
    def _text_from_response(payload: dict, *, strip: bool = True) -> str:
        try:
            parts = payload["candidates"][0]["content"]["parts"]
            text = "".join(part.get("text", "") for part in parts)
            return text.strip() if strip else text
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMUnavailableError("Gemini returned no text candidate.") from exc

    @staticmethod
    def _check_response(response: httpx.Response) -> None:
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            try:
                body = response.json()
                detail = body.get("error", {}).get("message", "")
            except (ValueError, AttributeError):
                detail = ""
            detail = detail or response.reason_phrase
            # The credential is sent only in a header and is never included in
            # this diagnostic; the API's message helps distinguish key/model
            # errors from temporary provider outages.
            raise LLMUnavailableError(f"Gemini API HTTP {response.status_code}: {detail}") from exc

    def _generate(self, system_prompt: str, user_message: str, *, json_mode: bool = False) -> str:
        if not self.api_key:
            raise LLMUnavailableError("GEMINI_API_KEY is not set.")
        try:
            last_error = None
            models = list(dict.fromkeys([self.model, self.fallback_model]))
            for model_index, model in enumerate(models):
                for attempt in range(2):
                    response = httpx.post(
                        self._url(model=model),
                        headers={"x-goog-api-key": self.api_key},
                        json=self._request_body(system_prompt, user_message, json_mode=json_mode),
                        timeout=45.0,
                    )
                    if response.status_code in {500, 502, 503}:
                        try:
                            detail = response.json().get("error", {}).get("message", "")
                        except (ValueError, AttributeError):
                            detail = ""
                        last_error = LLMUnavailableError(
                            f"Gemini API HTTP {response.status_code}: {detail or response.reason_phrase}"
                        )
                        if attempt == 0:
                            time.sleep(0.4)
                            continue
                        break
                    self._check_response(response)
                    return self._text_from_response(response.json())
                log.warning("Gemini model %s unavailable; trying configured fallback model", model)
            raise last_error or LLMUnavailableError("Gemini models are unavailable.")
        except LLMUnavailableError:
            raise
        except Exception as exc:  # noqa: BLE001 -- upstream errors use safe local fallback
            raise LLMUnavailableError(f"Gemini request failed: {exc}") from exc

    def complete_json(self, system_prompt: str, user_message: str) -> str:
        return self._generate(system_prompt, user_message, json_mode=True)

    def complete_text(self, system_prompt: str, user_message: str) -> str:
        return self._generate(system_prompt, user_message)

    def stream_text(self, system_prompt: str, user_message: str):
        if not self.api_key:
            raise LLMUnavailableError("GEMINI_API_KEY is not set.")
        try:
            with httpx.stream(
                "POST",
                self._url(streaming=True),
                headers={"x-goog-api-key": self.api_key},
                json=self._request_body(system_prompt, user_message),
                timeout=45.0,
            ) as response:
                self._check_response(response)
                for line in response.iter_lines():
                    if not line.startswith("data:"):
                        continue
                    chunk = line[5:].strip()
                    if not chunk or chunk == "[DONE]":
                        continue
                    text = self._text_from_response(json.loads(chunk), strip=False)
                    if text:
                        yield text
        except LLMUnavailableError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise LLMUnavailableError(f"Gemini streaming request failed: {exc}") from exc


def build_llm_client():
    """Choose the configured provider without ever exposing its API key.

    ``auto`` preserves existing Groq installations, supports a dedicated
    GEMINI_API_KEY, and recognizes Google AI Studio keys left in the old
    GROQ_API_KEY setting while users migrate their .env file.
    """
    settings = get_settings()
    provider = settings.llm_provider.strip().lower()
    gemini_key = settings.gemini_api_key
    groq_key = settings.groq_api_key

    if provider == "gemini":
        return GeminiClient(api_key=gemini_key or groq_key) if (gemini_key or groq_key) else None
    if provider == "groq":
        return GroqClient() if groq_key else None
    if provider != "auto":
        log.warning("Unknown LLM_PROVIDER=%r; disabling optional language model", provider)
        return None
    if gemini_key:
        return GeminiClient(api_key=gemini_key)
    if groq_key.startswith("AIza"):
        return GeminiClient(api_key=groq_key)
    if groq_key:
        return GroqClient()
    return None
