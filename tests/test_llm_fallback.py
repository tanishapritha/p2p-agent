import asyncio
import json

import httpx
import pytest
from pydantic import ValidationError

from app.config import settings
from app.llm import LLMNotConfigured, extract_invoice_with_llm


def _valid_invoice_payload() -> dict:
    return {
        "invoice_number": "INV-1001",
        "vendor_name": "Acme Supplies",
        "po_number": "PO-1001",
        "grn_number": "GRN-1001",
        "currency": "inr",
        "subtotal": 100.0,
        "tax": 18.0,
        "total": 118.0,
        "line_items": [{"description": "Laptop", "quantity": 2, "unit_price": 50.0}],
        "missing_fields": [],
        "uncertainties": [],
    }


def _make_chat_response(url: str, content: str, model: str) -> httpx.Response:
    request = httpx.Request("POST", url)
    return httpx.Response(
        200,
        request=request,
        json={
            "model": model,
            "usage": {"total_tokens": 42},
            "choices": [{"message": {"content": content}}],
        },
    )


def test_primary_succeeds_without_openrouter(monkeypatch):
    calls: list[tuple[str, dict, dict]] = []

    async def fake_post(self, url: str, headers: dict, json: dict):
        calls.append((url, headers, json))
        return _make_chat_response(url, json_module.dumps(_valid_invoice_payload()), "gpt-4o-mini")

    json_module = json
    monkeypatch.setattr(settings, "llm_api_key", "primary-key")
    monkeypatch.setattr(settings, "llm_base_url", "https://api.openai.com/v1")
    monkeypatch.setattr(settings, "llm_model", "gpt-4o-mini")
    monkeypatch.setattr(settings, "openrouter_api_key", "openrouter-key")
    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    result = asyncio.run(extract_invoice_with_llm("Invoice INV-1001"))

    assert len(calls) == 1
    assert calls[0][0] == "https://api.openai.com/v1/chat/completions"
    assert calls[0][2]["model"] == "gpt-4o-mini"
    assert result["invoice_number"] == "INV-1001"
    assert result["currency"] == "INR"
    assert result["_model"] == "gpt-4o-mini"


def test_primary_failure_falls_back_to_openrouter_success(monkeypatch):
    calls: list[tuple[str, dict, dict]] = []

    async def fake_post(self, url: str, headers: dict, json: dict):
        calls.append((url, headers, json))
        if len(calls) == 1:
            raise httpx.ConnectError("primary unavailable", request=httpx.Request("POST", url))
        fenced = f"```json\n{json_module.dumps(_valid_invoice_payload())}\n```"
        return _make_chat_response(url, fenced, "google/gemma-4-26b-a4b-it:free")

    json_module = json
    monkeypatch.setattr(settings, "llm_api_key", "primary-key")
    monkeypatch.setattr(settings, "llm_base_url", "https://api.openai.com/v1")
    monkeypatch.setattr(settings, "llm_model", "gpt-4o-mini")
    monkeypatch.setattr(settings, "openrouter_api_key", "openrouter-key")
    monkeypatch.setattr(settings, "openrouter_base_url", "https://openrouter.ai/api/v1")
    monkeypatch.setattr(settings, "openrouter_model", "google/gemma-4-26b-a4b-it:free")
    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    result = asyncio.run(extract_invoice_with_llm("Invoice INV-1001"))

    assert len(calls) == 2
    assert calls[0][0] == "https://api.openai.com/v1/chat/completions"
    assert calls[1][0] == "https://openrouter.ai/api/v1/chat/completions"
    assert calls[1][1]["Authorization"] == "Bearer openrouter-key"
    assert calls[1][2]["model"] == "google/gemma-4-26b-a4b-it:free"
    assert calls[1][2]["messages"] == calls[0][2]["messages"]
    assert calls[1][2]["response_format"] == calls[0][2]["response_format"]
    assert result["invoice_number"] == "INV-1001"
    assert result["currency"] == "INR"
    assert result["_model"] == "google/gemma-4-26b-a4b-it:free"


def test_openrouter_fallback_failure_raises(monkeypatch):
    async def fake_post(self, url: str, headers: dict, json: dict):
        request = httpx.Request("POST", url)
        return httpx.Response(502, request=request, text="bad gateway")

    monkeypatch.setattr(settings, "llm_api_key", "primary-key")
    monkeypatch.setattr(settings, "openrouter_api_key", "openrouter-key")
    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    with pytest.raises(httpx.HTTPStatusError):
        asyncio.run(extract_invoice_with_llm("Invoice INV-1001"))


def test_openrouter_fallback_invalid_schema_raises_validation_error(monkeypatch):
    calls: list[str] = []

    async def fake_post(self, url: str, headers: dict, json: dict):
        calls.append(url)
        if len(calls) == 1:
            raise httpx.ConnectError("primary down", request=httpx.Request("POST", url))
        invalid_payload = {"invoice_number": "INV-1001", "unexpected_field": True}
        return _make_chat_response(
            url,
            json_module.dumps(invalid_payload),
            "google/gemma-4-26b-a4b-it:free",
        )

    json_module = json
    monkeypatch.setattr(settings, "llm_api_key", "primary-key")
    monkeypatch.setattr(settings, "openrouter_api_key", "openrouter-key")
    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    with pytest.raises(ValidationError):
        asyncio.run(extract_invoice_with_llm("Invoice INV-1001"))


def test_neither_provider_configured_raises(monkeypatch):
    monkeypatch.setattr(settings, "llm_api_key", "")
    monkeypatch.setattr(settings, "openrouter_api_key", "")

    with pytest.raises(LLMNotConfigured):
        asyncio.run(extract_invoice_with_llm("Invoice INV-1001"))
