# Project State

> Source of truth for the committed implementation. "Implemented" means code exists; it does not imply runtime verification.

## Objective and problem
Resolve PO-backed invoice exceptions by interpreting invoice documents, retrieving authoritative P2P records and applying deterministic financial rules. AI assists extraction/investigation; Python owns arithmetic and match decisions. Recommendations route to a human. The system has no payment execution capability.

## Domain concepts
Vendor; purchase order and PO lines; goods receipt note and received lines; invoice and invoice lines; financial policy/tolerances; exception case; agent run/event; evaluation run. Invoice identity is unique per vendor + invoice number. Money uses SQL NUMERIC/Decimal.

## Functional requirements and current coverage
- PDF upload, PyMuPDF text extraction, Tesseract fallback: implemented in app/ingestion.py and API upload route.
- Real LLM structured extraction: implemented using configured OpenAI-compatible chat-completions endpoint in app/llm.py. Missing key returns BLOCKED/503; no mock fallback.
- Pydantic extraction validation and missing/uncertainty fields: implemented in app/schemas.py.
- SQLAlchemy domain models and Alembic initial migration: implemented.
- Typed P2P read/write tool functions: partial in app/tools.py; not yet exposed as model-callable LangGraph tools or all fully covered by tests.
- Deterministic three-way matching: partial in app/matching.py; price/quantity, GRN receipt, currency, vendor/duplicate flags, subtotal and total checks. Fail-closed for missing PO/GRN lines. It currently accepts caller-supplied found/match flags and does not resolve/verify PO-GRN-vendor relationships itself.
- API: health, readiness, PDF extraction, deterministic match, invoice list, case list.
- Streamlit: basic extraction/match/case console calling HTTP endpoints.
- Docker, Compose, CI and basic unit tests: files committed, not runtime-verified.

## Architecture
Modular monolith: FastAPI -> Pydantic -> SQLAlchemy/PostgreSQL; ingestion -> real LLM provider adapter -> validated extraction; matching is a pure deterministic function; Streamlit calls HTTP APIs. No microservices or unnecessary infrastructure.

## Agent and LangGraph
LangGraph is a declared dependency only. A stateful production graph, conditional routing, checkpoint persistence, retry/recovery, model tool-calling loop, human interrupt/resume and audit-complete approval flow are NOT implemented. Do not describe the current application as a working agent yet.

## Tools
app/tools.py provides get_invoice, find_vendor, find_purchase_order, get_goods_receipt, get_vendor_history, get_financial_policy, run_three_way_match_tool, get_supporting_evidence and create_exception_case. These use actual SQLAlchemy sessions. They are not yet registered as LLM-callable tools, and comprehensive tool authorization/tests are outstanding.

## Database schema
app/models.py defines vendors, purchase_orders, po_lines, goods_receipts, grn_lines, invoices, invoice_lines, financial_policies, exception_cases, agent_runs, agent_events and evaluation_runs. Alembic's 0001_initial migration creates the current metadata. The migration has not been applied against a live database in this environment. No checkpoint table or evaluation-result table is implemented.

## PDF and extraction
POST /invoices/upload accepts PDFs up to MAX_UPLOAD_MB, extracts text via PyMuPDF and attempts Tesseract OCR when no text exists. It calls the configured real OpenAI-compatible endpoint with strict JSON schema output, then validates with ExtractedInvoice. The current endpoint returns EXTRACTED_NOT_PERSISTED and deletes the temporary file; vendor resolution and trusted invoice persistence are not yet implemented. Malformed PDF, missing Tesseract and missing API key return explicit errors. Document text is treated as untrusted content in the extraction prompt.

## Deterministic matching
app/matching.py uses Decimal and Pydantic. It compares line count/descriptions, quantities, unit prices, GRN received quantities, currency, subtotal and total; accepts duplicate/vendor mismatch flags; missing PO/GRN and empty source lines hold. It does not yet resolve ambiguous descriptions beyond exact normalized string equality, compare tax rates against a policy, validate PO-GRN linkage, or retrieve its own source records. Never treat this standalone endpoint as a verified production payment control.

## Evaluation
NOT IMPLEMENTED. There is no synthetic dataset, separate ground-truth store, evaluator CLI, offline/live evaluation runner, metrics, quality gate or LLM judge. No scores have been fabricated.

## Observability and security
No persisted run-event pipeline, SSE streaming, Langfuse or OpenTelemetry integration is implemented. Basic errors are returned through FastAPI. PDF content is treated as untrusted; upload size/type checks exist; no bank/payment operations exist. Authentication/authorization, reviewer identity and approval controls are NOT implemented. Do not expose this API to untrusted networks.

## API routes actually present
- GET /health
- GET /ready (checks DB connection)
- POST /invoices/upload (real provider call; extraction only, not persisted)
- POST /matching/evaluate (deterministic calculation from supplied payload)
- GET /invoices
- GET /cases

## Environment variables
APP_ENV, DATABASE_URL, LLM_BASE_URL, LLM_API_KEY, LLM_MODEL, LLM_TIMEOUT_SECONDS, UPLOAD_DIR, MAX_UPLOAD_MB, TESSERACT_CMD, LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY, LANGFUSE_HOST. Langfuse variables are reserved and currently unused. See .env.example.

## Actual repository structure
```
.github/workflows/ci.yml
app/__init__.py
app/config.py
app/db.py
app/ingestion.py
app/llm.py
app/main.py
app/matching.py
app/models.py
app/schemas.py
app/tools.py
console/app.py
migrations/env.py
migrations/script.py.mako
migrations/versions/0001_initial.py
tests/test_matching.py
alembic.ini
docker-compose.yml
Dockerfile
pyproject.toml
requirements-dev.txt
.env.example
.gitignore
.dockerignore
README.md
PROJECT_STATE.md
TESTING_GUIDE.md
IMPLEMENTATION_LOG.md
```

## Setup and execution
PowerShell: create/activate Python 3.11 venv; pip install -e ".[dev]"; copy .env.example to .env and set DATABASE_URL; start PostgreSQL; alembic upgrade head; uvicorn app.main:app --reload; in another terminal streamlit run console/app.py. See TESTING_GUIDE.md. Docker Compose requires .env and Docker installed.

## Testing strategy and observed status
tests/test_matching.py contains four deterministic unit tests. No test command has been executed in this remote GitHub editing session. PostgreSQL integration, live LLM, LangGraph, security, API end-to-end and tracing tests are not present. CI workflow exists but has not run. Treat every test as NOT RUN until a real runner reports otherwise.

## Deployment approach
Local-only developer setup via FastAPI, PostgreSQL and Streamlit; Docker Compose scaffold. Not production-ready. Add auth, secret management, TLS, migrations review, persistent workflow checkpoints, observability, backups and threat-model validation before deployment.

## Decisions and exclusions
- Decimal/Python for all financial decisions.
- One modular monolith; no microservices/Kubernetes/Kafka/Redis/vector DB.
- Real provider only; missing credentials are errors.
- No payment execution or bank-detail mutation.
- No mock model responses, fabricated traces or fake evaluation results.

## Implementation status
Implemented in code: database models, initial migration, provider-backed PDF extraction, Pydantic extraction schema, deterministic match function, DB tool functions, basic API, basic Streamlit console, Docker/Compose/CI scaffold and four unit tests.
Partially implemented: database-backed API, OCR fallback, P2P tools, matching coverage, developer console.
Not implemented: full LangGraph agent, model tool loop, durable checkpoint/human approval, full CRUD/seed workflow, event/SSE/trace pipeline, evaluation engine/dataset, auth, integration/live/E2E tests, production hardening.
Tested and passed: none observed in this remote session.
Tested and failed: none observed.
Not tested: all application tests, migrations, Docker and CI.
Blocked: real LLM/PDF run requires user-supplied provider credentials; PostgreSQL integration requires a running database. GitHub connector cannot run local commands.

## Known limitations and next steps
1. Add real DB-backed invoice creation/vendor/PO/GRN APIs and verify relationships before matching.
2. Add LangGraph nodes, tool registration, durable PostgreSQL checkpointing, idempotency and human authorization/resume.
3. Add persisted events/SSE and optional Langfuse/OTel.
4. Add synthetic database dataset with separately stored ground truth and actual-agent offline/live evaluation.
5. Expand Streamlit run explorer/evaluation/dataset/health tabs through APIs.
6. Add auth, API rate/file controls, integration/live/E2E tests and operational security.
7. Run tests/migrations/CI in a real environment and update the log with observed output.
