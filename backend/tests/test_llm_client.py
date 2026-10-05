import httpx
import pytest

from app.nlp.llm_client import GeminiClient, LLMUnavailableError


def test_gemini_json_uses_configured_endpoint_and_auth_header(monkeypatch):
    calls = {}

    def fake_post(url, *, headers, json, timeout):
        calls.update(url=url, headers=headers, body=json, timeout=timeout)
        return httpx.Response(
            200,
            json={"candidates": [{"content": {"parts": [{"text": '{"intent":"DEMAND_FORECAST"}'}]}}]},
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx, "post", fake_post)
    client = GeminiClient(api_key="unit-test-key", model="gemini-test-model")

    result = client.complete_json("system", "question")

    assert result == '{"intent":"DEMAND_FORECAST"}'
    assert calls["url"].endswith("/gemini-test-model:generateContent")
    assert calls["headers"] == {"x-goog-api-key": "unit-test-key"}
    assert calls["body"]["generationConfig"]["responseMimeType"] == "application/json"


def test_gemini_reports_provider_error_without_exposing_key(monkeypatch):
    def fake_post(url, **kwargs):
        return httpx.Response(
            503,
            json={"error": {"message": "temporarily unavailable"}},
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx, "post", fake_post)
    client = GeminiClient(api_key="never-print-this-key")

    with pytest.raises(LLMUnavailableError, match="Gemini API HTTP 503: temporarily unavailable") as error:
        client.complete_text("system", "question")

    assert "never-print-this-key" not in str(error.value)


def test_gemini_uses_fallback_model_after_transient_primary_outage(monkeypatch):
    urls = []

    def fake_post(url, **kwargs):
        urls.append(url)
        if "gemini-primary" in url:
            return httpx.Response(
                503,
                json={"error": {"message": "busy"}},
                request=httpx.Request("POST", url),
            )
        return httpx.Response(
            200,
            json={"candidates": [{"content": {"parts": [{"text": "recognized"}]}}]},
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx, "post", fake_post)
    monkeypatch.setattr("app.nlp.llm_client.time.sleep", lambda _: None)
    client = GeminiClient(api_key="unit-test-key", model="gemini-primary")
    client.fallback_model = "gemini-fallback"

    assert client.complete_text("system", "question") == "recognized"
    assert urls == [
        "https://generativelanguage.googleapis.com/v1beta/models/gemini-primary:generateContent",
        "https://generativelanguage.googleapis.com/v1beta/models/gemini-primary:generateContent",
        "https://generativelanguage.googleapis.com/v1beta/models/gemini-fallback:generateContent",
    ]
