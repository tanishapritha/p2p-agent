# Project State

> This file reflects the committed source snapshot. Code existence is not proof of runtime correctness. No local tests or app commands have been executed in this editing session.

## System
A modular FastAPI + PostgreSQL + SQLAlchemy app. PDF invoice text extraction and OCR fallback, real OpenAI-compatible structured extraction, deterministic financial matching, and a LangGraph workflow that resolves invoice-linked records and persists run/event data. Streamlit workbench calls API endpoints. The system is recommendation/review only and never executes payments.

## Implemented files and capabilities
- `app/ingestion.py`: PDF text extraction with OCR fallback.
- `app/llm.py`: real provider structured extraction. No fake response fallback; key required.
- `app/schemas.py`: validation for extracted invoices/line items.
- `app/matching.py`: Decimal deterministic match checks, totals, duplicate/vendor flags, fail-closed missing source records.
- `app/tools.py`: DB functions for invoice/vendor/PO/GRN/history/policy/evidence/case operations.
- `app/agent.py`: LangGraph nodes for record resolution, deterministic matching, and review recommendation; graph invocation; persisted run and event records; idempotency key check.
- `app/main.py`: health/readiness, extraction, deterministic matching, invoice/case list, agent run, run/event retrieval and human-review record endpoints.
- `app/models.py`, Alembic migrations 0001/0002: domain tables plus agent run state/result, idempotency key, reviewer/note, update timestamp.
- `console/app.py`: Streamlit PDF extraction, match test, case display, run explorer and review form.
- `app/evaluate.py`, `eval/datasets/matching_v1.jsonl`: offline deterministic matcher evaluation over labeled synthetic cases (not production transaction data).
- ``tests/test_matching.py`, `tests/test_evaluate.py`: four matcher unit tests plus one synthetic dataset evaluator test.
- Docker, Compose and GitHub Actions CI scaffold.

## Agent behavior
The graph loads invoice by ID, resolves the invoice's PO and GRN references, checks PO vendor and GRN-to-PO linkage, and feeds authoritative records into the deterministic matcher. It writes run/event records and sets `AWAITING_HUMAN_REVIEW`. Review endpoint records `ACKNOWLEDGE` or `DISPUTE` and marks `HUMAN_REVIEWED`; this is not payment approval.

## Routes
- `GET /health`, `GET /ready`
- `POST /invoices/upload` — extraction only; not persisted\n- `POST /invoices/confirm` — human-confirmed extracted data is persisted after vendor ID validation\n- `POST /master-data/vendors`, `/master-data/purchase-orders`, `/master-data/goods-receipts` — development-only local master-data entry
- `POST /matching/evaluate` — caller-supplied payload; not authoritative
- `GET /invoices`, `GET /cases`
- `POST /agent/invoices/{invoice_id}/run`
- `GET /agent/runs/{run_id}`
- `POST /agent/runs/{run_id}/review`

## Evaluation
The dataset and CLI test the deterministic matching function only. They do not evaluate LLM extraction, the full LangGraph agent, or production transaction data. Run with:
`python -m app.evaluate --dataset eval/datasets/matching_v1.jsonl`
No scores are claimed because the evaluator has not been run here.

## Still incomplete / risk
- No local execution, pytest, Ruff, Alembic, Docker or CI run performed; no observed passing checks. GitHub commit workflow/status retrieval returned no workflow runs/statuses.
- Upload extraction remains non-persistent until a human calls invoice confirmation. No master-data import/UI exists; development-only API entry endpoints are present. Invoice confirmation and review endpoints trust caller-supplied reviewer identifiers and do not authenticate identity.
- No LangGraph durable checkpoint/resume, conditional recovery/ retry logic, or LLM-driven investigation/tool-calling loop. This is a deterministic LangGraph workflow, not autonomous AI decision-making.
- Human review API lacks authentication/authorization and reviewer identity verification. It is not safe for public deployment.
- No trace telemetry, SSE, Langfuse/OTel, full agent evaluation, integration/live/E2E tests, security hardening or production ops.
- Matching still has limitations: exact normalized descriptions, caller flags in standalone route, simplistic tax checks, and no full configurable policy model.

## Setup
Use README and TESTING_GUIDE.md. Configure a real PostgreSQL database and provider API key. The agent run API requires an invoice already stored in PostgreSQL, which upload does not create yet. Local or manually seeded records are required.

## Test evidence
- Tested and passed: none observed.
- Tested and failed: none observed.
- Not run: pytest, Ruff, migrations, API, graph, evaluation CLI, Docker and CI.
