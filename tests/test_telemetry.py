import asyncio
import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import httpx
from fastapi import FastAPI
from sqlalchemy import create_engine

from app import agent, telemetry
from app.config import settings
from app.llm import extract_invoice_with_llm


def test_span_export_filter_includes_fastapi_sqlalchemy_and_langfuse():
    langfuse_span = SimpleNamespace(
        instrumentation_scope=SimpleNamespace(name="langfuse-sdk"),
        attributes={},
    )
    fastapi_span = SimpleNamespace(
        instrumentation_scope=SimpleNamespace(name="opentelemetry.instrumentation.fastapi"),
        attributes={},
    )
    sqla_span = SimpleNamespace(
        instrumentation_scope=SimpleNamespace(name="opentelemetry.instrumentation.sqlalchemy"),
        attributes={},
    )
    unrelated_span = SimpleNamespace(
        instrumentation_scope=SimpleNamespace(name="some.unrelated.library"),
        attributes={},
    )

    assert telemetry.should_export_langfuse_span(langfuse_span) is True
    assert telemetry.should_export_langfuse_span(fastapi_span) is True
    assert telemetry.should_export_langfuse_span(sqla_span) is True
    assert telemetry.should_export_langfuse_span(unrelated_span) is False


def test_mask_sensitive_data_redacts_financial_and_credential_fields():
    payload = {
        "agent_run_id": "42",
        "vendor_name": "Acme Corp",
        "invoice_number": "INV-99",
        "total": "1234.56",
        "api_key": "sk-secret",
        "nested": {"subtotal": 100, "status": "MATCHED"},
    }
    masked = telemetry.mask_sensitive_data(payload)
    assert masked["agent_run_id"] == "42"
    assert masked["vendor_name"] == "[REDACTED]"
    assert masked["invoice_number"] == "[REDACTED]"
    assert masked["total"] == "[REDACTED]"
    assert masked["api_key"] == "[REDACTED]"
    assert masked["nested"]["subtotal"] == "[REDACTED]"
    assert masked["nested"]["status"] == "MATCHED"


def test_init_telemetry_instruments_fastapi_and_sqlalchemy_once(monkeypatch):
    telemetry.reset_telemetry_state_for_tests()
    monkeypatch.setattr(settings, "langfuse_public_key", "")
    monkeypatch.setattr(settings, "langfuse_secret_key", "")

    fastapi_calls = []
    sqla_calls = []

    monkeypatch.setattr(
        telemetry.FastAPIInstrumentor,
        "instrument_app",
        lambda app: fastapi_calls.append(app),
    )
    mock_sqla = MagicMock()
    mock_sqla.instrument.side_effect = lambda **kw: sqla_calls.append(kw)
    monkeypatch.setattr(telemetry, "SQLAlchemyInstrumentor", lambda: mock_sqla)

    app = FastAPI()
    engine = create_engine("sqlite:///:memory:")
    telemetry.init_telemetry(app, engine)
    telemetry.init_telemetry(app, engine)

    assert len(fastapi_calls) == 1
    assert len(sqla_calls) == 1
    assert sqla_calls[0]["engine"] is engine
    assert sqla_calls[0]["enable_commenter"] is False
    telemetry.reset_telemetry_state_for_tests()


def test_agent_run_correlates_trace_with_agent_run_id(monkeypatch):
    captured_context: dict = {}
    captured_invoke: dict = {}

    class DummyRun:
        id = 77

    class DummySession:
        def get(self, _model, _id):
            return SimpleNamespace(id=1)

        def add(self, _obj):
            pass

        def commit(self):
            pass

        def refresh(self, obj):
            obj.id = 77

        def close(self):
            pass

    def fake_propagate(**kwargs):
        captured_context.update(kwargs)
        from contextlib import nullcontext

        return nullcontext()

    monkeypatch.setattr(agent, "SessionLocal", lambda: DummySession())
    monkeypatch.setattr(agent, "_event", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(agent, "propagate_trace_context", fake_propagate)
    monkeypatch.setattr(agent, "get_langchain_callbacks", lambda: ["cb-handler"])
    monkeypatch.setattr(
        agent.invoice_exception_graph,
        "invoke",
        lambda state, config=None: (
            captured_invoke.update({"state": state, "config": config})
            or {"status": "AWAITING_HUMAN_REVIEW", "result": {"recommendation": "HOLD_FOR_REVIEW"}}
        ),
    )

    res = agent.run_invoice_agent(invoice_id=1)

    assert res["run_id"] == 77
    assert captured_context["agent_run_id"] == 77
    assert captured_context["workflow_name"] == "invoice_exception_workflow"
    assert captured_context["metadata"]["agent_run_id"] == "77"
    assert captured_invoke["config"] == {"callbacks": ["cb-handler"]}


def test_telemetry_failure_does_not_break_llm_extraction(monkeypatch):
    telemetry.reset_telemetry_state_for_tests()
    monkeypatch.setattr(settings, "langfuse_public_key", "pk-test")
    monkeypatch.setattr(settings, "langfuse_secret_key", "sk-test")
    monkeypatch.setattr(settings, "llm_api_key", "primary-key")
    monkeypatch.setattr(settings, "openrouter_api_key", "")

    class BrokenLangfuseClient:
        def start_as_current_observation(self, **_kwargs):
            raise RuntimeError("langfuse down")

    monkeypatch.setattr(telemetry, "get_langfuse_client", lambda: BrokenLangfuseClient())

    async def fake_post(self, url: str, headers: dict, json: dict):
        return httpx.Response(
            200,
            request=httpx.Request("POST", url),
            json={
                "model": "gpt-4o-mini",
                "usage": {"total_tokens": 10},
                "choices": [
                    {
                        "message": {
                            "content": json_mod.dumps(
                                {
                                    "invoice_number": "INV-1",
                                    "vendor_name": "Acme",
                                    "po_number": None,
                                    "grn_number": None,
                                    "currency": "INR",
                                    "subtotal": 10,
                                    "tax": 0,
                                    "total": 10,
                                    "line_items": [
                                        {"description": "Item", "quantity": 1, "unit_price": 10}
                                    ],
                                    "missing_fields": [],
                                    "uncertainties": [],
                                }
                            )
                        }
                    }
                ],
            },
        )

    json_mod = json
    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    result = asyncio.run(extract_invoice_with_llm("Invoice INV-1"))
    assert result["invoice_number"] == "INV-1"
    telemetry.reset_telemetry_state_for_tests()
