# P2P Invoice Exception Agent

A modular-monolith starter for PO-backed invoice exception resolution. Financial matching is deterministic Python; an LLM may interpret documents and investigate via controlled tools. Recommendations are never payment authorization.

## Quick start
1. Python 3.11+, PostgreSQL 15+, optional Tesseract.
2. `py -3.11 -m venv .venv; .\.venv\Scripts\Activate.ps1`
3. `pip install -e ".[dev]"`
4. Copy `.env.example` to `.env`, configure `DATABASE_URL` and an actual provider key.
5. `alembic upgrade head`
6. `uvicorn app.main:app --reload`
7. `streamlit run console/app.py`

See [TESTING_GUIDE.md](TESTING_GUIDE.md), [PROJECT_STATE.md](PROJECT_STATE.md) and [IMPLEMENTATION_LOG.md](IMPLEMENTATION_LOG.md). Do not treat missing provider credentials as a successful LLM run.

## Current scope
Includes a LangGraph orchestration workflow that resolves invoice-linked vendor/PO/GRN records from PostgreSQL, runs deterministic matching, persists agent-run state/events, and leaves results awaiting human review. API endpoints expose run initiation, run/event retrieval, and reviewer acknowledgement/dispute recording. A basic Streamlit agent-run tab and offline deterministic evaluation script/dataset are also included.

**Important status:** code has been committed but not executed in this environment. Database schema/migrations, API, workflow, UI, evaluator and CI must be verified locally or by GitHub Actions before relying on it. Upload extraction is not automatic; a new explicit confirmation endpoint can persist validated extracted fields after vendor selection, but the reviewer identifier is not authenticated. Authentication, full CRUD/seed workflow, durable LangGraph checkpoints/resume, provider-backed investigation tool calls, full telemetry, and production deployment controls remain outstanding. The agent does not authorize or execute payments.
