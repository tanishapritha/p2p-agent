"""Langfuse and OpenTelemetry observability with fail-safe redaction."""

from __future__ import annotations

import logging
import os
import time
from contextlib import contextmanager
from typing import Any

from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.sdk.trace import ReadableSpan

from app.config import settings

logger = logging.getLogger(__name__)

EXPORTED_OTEL_SCOPE_PREFIXES = (
    "opentelemetry.instrumentation.fastapi",
    "opentelemetry.instrumentation.asgi",
    "opentelemetry.instrumentation.sqlalchemy",
)

SENSITIVE_KEYS = frozenset(
    {
        "api_key",
        "apikey",
        "authorization",
        "secret",
        "secret_key",
        "token",
        "password",
        "passwd",
        "vendor_name",
        "supplier",
        "supplier_name",
        "invoice_number",
        "po_number",
        "grn_number",
        "subtotal",
        "tax",
        "total",
        "unit_price",
        "amount",
        "raw_text",
        "document_text",
        "pdf",
        "source_path",
        "extraction",
        "reviewer",
        "review_note",
        "note",
        "database_url",
        "direct_database_url",
    }
)

_langfuse_client: Any = None
_langfuse_initialized = False
_fastapi_instrumented = False
_sqlalchemy_instrumented = False


class _NoOpObservation:
    """Fallback observation handle when telemetry is disabled or fails."""

    def update(self, **_kwargs: Any) -> None:
        return None


def is_telemetry_configured() -> bool:
    return bool(settings.langfuse_public_key and settings.langfuse_secret_key)


def get_langfuse_base_url() -> str:
    return settings.langfuse_base_url or settings.langfuse_host or "https://cloud.langfuse.com"


def mask_sensitive_data(data: Any) -> Any:
    """Recursively redact sensitive invoice, supplier, financial, and credential fields."""
    if isinstance(data, dict):
        masked: dict[str, Any] = {}
        for key, value in data.items():
            key_lower = str(key).lower()
            if key_lower in SENSITIVE_KEYS or any(
                part in key_lower for part in ("secret", "password", "api_key", "token")
            ):
                masked[key] = "[REDACTED]"
            else:
                masked[key] = mask_sensitive_data(value)
        return masked
    if isinstance(data, list):
        return [mask_sensitive_data(item) for item in data]
    if isinstance(data, tuple):
        return tuple(mask_sensitive_data(item) for item in data)
    return data


def should_export_langfuse_span(span: ReadableSpan) -> bool:
    """Export Langfuse/LLM spans plus FastAPI and SQLAlchemy OpenTelemetry spans."""
    try:
        from langfuse import is_default_export_span

        if is_default_export_span(span):
            return True
    except Exception:  # noqa: BLE001 - span filter must never break OTel export
        return False
    scope = getattr(span, "instrumentation_scope", None)
    scope_name = getattr(scope, "name", "") if scope else ""
    return scope_name.startswith(EXPORTED_OTEL_SCOPE_PREFIXES)


def get_langfuse_client() -> Any:
    """Initialize and return the shared Langfuse client, or None if unconfigured/failed."""
    global _langfuse_client, _langfuse_initialized
    if _langfuse_initialized:
        return _langfuse_client
    _langfuse_initialized = True
    if not is_telemetry_configured():
        return None
    try:
        from langfuse import Langfuse

        base_url = get_langfuse_base_url()
        os.environ.setdefault("LANGFUSE_PUBLIC_KEY", settings.langfuse_public_key)
        os.environ.setdefault("LANGFUSE_SECRET_KEY", settings.langfuse_secret_key)
        os.environ.setdefault("LANGFUSE_BASE_URL", base_url)
        _langfuse_client = Langfuse(
            public_key=settings.langfuse_public_key,
            secret_key=settings.langfuse_secret_key,
            base_url=base_url,
            environment=settings.app_env,
            should_export_span=should_export_langfuse_span,
            mask=mask_sensitive_data,
        )
    except Exception as exc:  # noqa: BLE001 - telemetry init must never break app startup
        logger.warning("Langfuse initialization disabled due to error: %s", type(exc).__name__)
        _langfuse_client = None
    return _langfuse_client


def instrument_fastapi(app: Any) -> bool:
    """Attach OpenTelemetry FastAPI instrumentation once, reusing the active TracerProvider."""
    global _fastapi_instrumented
    if _fastapi_instrumented:
        return True
    try:
        FastAPIInstrumentor.instrument_app(app)
        _fastapi_instrumented = True
    except Exception as exc:  # noqa: BLE001 - telemetry failure must never break startup
        logger.warning("FastAPI OTel instrumentation failed: %s", type(exc).__name__)
        return False
    return True


def instrument_sqlalchemy(engine: Any) -> bool:
    """Attach OpenTelemetry SQLAlchemy instrumentation once to the given engine."""
    global _sqlalchemy_instrumented
    if _sqlalchemy_instrumented:
        return True
    try:
        SQLAlchemyInstrumentor().instrument(engine=engine, enable_commenter=False)
        _sqlalchemy_instrumented = True
    except Exception as exc:  # noqa: BLE001 - telemetry failure must never break startup
        logger.warning("SQLAlchemy OTel instrumentation failed: %s", type(exc).__name__)
        return False
    return True


def init_telemetry(app: Any, engine: Any) -> None:
    """Initialize Langfuse OTel TracerProvider first, then instrument FastAPI and SQLAlchemy."""
    get_langfuse_client()
    instrument_fastapi(app)
    instrument_sqlalchemy(engine)


def get_langchain_callbacks() -> list[Any]:
    """Return Langfuse LangChain CallbackHandler list if enabled, else empty list."""
    client = get_langfuse_client()
    if client is None:
        return []
    try:
        from langfuse.langchain import CallbackHandler

        return [CallbackHandler(public_key=settings.langfuse_public_key)]
    except Exception as exc:  # noqa: BLE001 - callback failure must never break workflow
        logger.warning("Langfuse CallbackHandler unavailable: %s", type(exc).__name__)
        return []


@contextmanager
def propagate_trace_context(
    *,
    agent_run_id: int | None = None,
    workflow_name: str | None = None,
    metadata: dict[str, Any] | None = None,
    tags: list[str] | None = None,
):
    """Propagate agent_run_id and safe metadata across LangGraph and OTel child spans."""
    client = get_langfuse_client()
    if client is None:
        yield
        return
    try:
        from langfuse import propagate_attributes

        safe_meta = mask_sensitive_data(metadata or {})
        if agent_run_id is not None:
            safe_meta["agent_run_id"] = str(agent_run_id)
        session_id = f"agent-run-{agent_run_id}" if agent_run_id is not None else None
        ctx = propagate_attributes(
            session_id=session_id,
            trace_name=workflow_name,
            metadata=safe_meta,
            tags=tags,
        )
        ctx.__enter__()
    except Exception as exc:  # noqa: BLE001 - propagation failure must never break workflow
        logger.warning("Langfuse attribute propagation failed: %s", type(exc).__name__)
        yield
        return

    try:
        yield
    finally:
        try:
            ctx.__exit__(None, None, None)
        except Exception as exc:  # noqa: BLE001 - cleanup must never mask application outcome
            logger.debug("Langfuse attribute cleanup failed: %s", type(exc).__name__)


@contextmanager
def observe_step(
    name: str,
    *,
    as_type: str = "span",
    metadata: dict[str, Any] | None = None,
    model: str | None = None,
):
    """Create a fail-safe Langfuse observation with latency and redacted metadata."""
    client = get_langfuse_client()
    if client is None:
        yield _NoOpObservation()
        return

    started = time.perf_counter()
    safe_meta = mask_sensitive_data(metadata or {})
    span_cm = None
    observation: Any = _NoOpObservation()
    try:
        kwargs: dict[str, Any] = {"name": name, "as_type": as_type, "metadata": safe_meta}
        if model is not None:
            kwargs["model"] = model
        span_cm = client.start_as_current_observation(**kwargs)
        observation = span_cm.__enter__()
    except Exception as exc:  # noqa: BLE001 - observation start failure must never break flow
        logger.warning("Langfuse observation '%s' failed to start: %s", name, type(exc).__name__)
        yield _NoOpObservation()
        return

    try:
        yield observation
    except Exception as exc:
        try:
            latency_ms = round((time.perf_counter() - started) * 1000, 2)
            observation.update(
                level="ERROR",
                status_message=type(exc).__name__,
                metadata={**safe_meta, "status": "FAILED", "latency_ms": latency_ms},
            )
        except Exception as exc_inner:  # noqa: BLE001 - never mask the original exception
            logger.debug("Langfuse error update failed: %s", type(exc_inner).__name__)
        raise
    else:
        try:
            latency_ms = round((time.perf_counter() - started) * 1000, 2)
            observation.update(metadata={**safe_meta, "latency_ms": latency_ms})
        except Exception as exc:  # noqa: BLE001 - never break flow on telemetry update
            logger.debug("Langfuse update failed: %s", type(exc).__name__)
    finally:
        if span_cm is not None:
            try:
                span_cm.__exit__(None, None, None)
            except Exception as exc:  # noqa: BLE001 - never break flow on telemetry close
                logger.debug("Langfuse observation close failed: %s", type(exc).__name__)


def reset_telemetry_state_for_tests() -> None:
    """Reset module-level initialization flags for isolated unit tests."""
    global _langfuse_client, _langfuse_initialized, _fastapi_instrumented, _sqlalchemy_instrumented
    _langfuse_client = None
    _langfuse_initialized = False
    _fastapi_instrumented = False
    _sqlalchemy_instrumented = False
