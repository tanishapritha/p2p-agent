# P2P Invoice Exception Agent

A modular-monolith starter for PO-backed invoice exception resolution. Financial matching is deterministic Python; an LLM may interpret documents and investigate via controlled tools. Recommendations are never payment authorization.

## Quick start (Neon PostgreSQL, no Docker required)

1. **Prerequisites:** Python 3.11+, a [Neon](https://neon.tech) PostgreSQL database, and optional Tesseract OCR.
2. **Create and activate a virtual environment:**
   ```powershell
   py -3.11 -m venv .venv
   .\.venv\Scripts\Activate.ps1
   pip install -e ".[dev]"
   ```
3. **Configure Neon connection strings:**
   - In the Neon Console, copy both the **Pooled** connection string (hostname includes `-pooler`) and the **Direct** connection string (hostname without `-pooler`).
   - Copy `.env.example` to `.env` and set:
     - `DATABASE_URL` to the Neon **pooled** URL (with `postgresql+psycopg://...`, `sslmode=require`). Used by the SQLAlchemy application engine.
     - `DIRECT_DATABASE_URL` to the Neon **direct** URL (with `postgresql+psycopg://...`, `sslmode=require`). Used by Alembic migrations.
     - Configure your LLM provider key (`LLM_API_KEY` and/or `OPENROUTER_API_KEY`).
4. **Run database migrations (uses `DIRECT_DATABASE_URL`):**
   ```powershell
   alembic upgrade head
   ```
   > Migrations are not run automatically on application startup; run `alembic upgrade head` manually when deploying or updating schema.
5. **Start the API and UI locally:**
   ```powershell
   uvicorn app.main:app --reload
   streamlit run console/app.py
   ```

## Observability (Langfuse + OpenTelemetry)

The API and LangGraph workflow integrate **Langfuse** (`langfuse>=3,<5`) and **OpenTelemetry** (`FastAPIInstrumentor` and `SQLAlchemyInstrumentor`) sharing Langfuse's `TracerProvider`:

1. Set `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, and `LANGFUSE_BASE_URL` (e.g. `https://cloud.langfuse.com`) in `.env`.
2. FastAPI HTTP spans, SQLAlchemy DB spans, LangGraph node executions (`CallbackHandler`), and custom observations (`invoice_extraction`, `llm_primary_extraction`, `llm_provider_fallback`, `vendor_po_grn_retrieval`, `three_way_matching`, `final_recommendation`) are exported under the same trace and correlated with `agent_run_id`.
3. Sensitive invoice, supplier, financial, and credential fields are redacted before export, and telemetry failures never block invoice processing.
4. To view a trace in Langfuse:
   - Start the API (`uvicorn app.main:app --reload`) and trigger an agent run (`POST /agent/invoices/{invoice_id}/run`) or upload (`POST /invoices/upload`).
   - Open your Langfuse project → **Traces** (or filter by **Session** `agent-run-<run_id>` or metadata `agent_run_id`).

## Optional: Local PostgreSQL with Docker Compose

If you prefer a local PostgreSQL instance instead of Neon:
1. Start the database container: `docker compose up -d db`
2. Set both `DATABASE_URL` and `DIRECT_DATABASE_URL` in `.env` to `postgresql+psycopg://p2p:p2p@localhost:5432/p2p_agent`.
3. Run `alembic upgrade head` and start the API/UI as above, or run `docker compose up --build` to start both `db` and `api`.

See [TESTING_GUIDE.md](TESTING_GUIDE.md), [PROJECT_STATE.md](PROJECT_STATE.md) and [IMPLEMENTATION_LOG.md](IMPLEMENTATION_LOG.md). Do not treat missing provider credentials as a successful LLM run.

## Current scope
Includes a LangGraph orchestration workflow that resolves invoice-linked vendor/PO/GRN records from PostgreSQL, runs deterministic matching, persists agent-run state/events, and leaves results awaiting human review. API endpoints expose run initiation, run/event retrieval, and reviewer acknowledgement/dispute recording. A basic Streamlit agent-run tab and offline deterministic evaluation script/dataset are also included.

**Important status:** code has been committed but not executed in this environment. Database schema/migrations, API, workflow, UI, evaluator and CI must be verified locally or by GitHub Actions before relying on it. Upload extraction is not automatic; the confirm endpoint persists extracted fields after vendor selection. Development-only master-data endpoints support local vendor/PO/GRN entry. Reviewer identity is not authenticated. Authentication, full CRUD/seed workflow, durable LangGraph checkpoints/resume, provider-backed investigation tool calls, full telemetry, and production deployment controls remain outstanding. The agent does not authorize or execute payments.
