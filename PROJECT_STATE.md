# Project State

> Living source of truth. Status is updated as implementation lands; planned components are not represented as implemented.

## Objective
Resolve purchase-order-backed invoice exceptions using AI for document interpretation and investigation, and deterministic Python for all financial matching and decisions. The system produces recommendations for authorized human review only. It never authorizes or executes payments.

## Domain
- **Vendor**: supplier identity and invoice history.
- **Purchase order (PO)**: approved order lines, quantities, unit prices, currency and tax expectations.
- **Goods receipt note (GRN)**: quantities actually received against a PO.
- **Invoice**: supplier claim, header totals, tax and one or more lines.
- **Three-way match**: deterministic comparison of invoice, PO and GRN, including tolerances.
- **Exception case**: auditable record of mismatches, evidence and recommendation.
- **Human decision**: separately authorized review action; never an agent action.

## Functional requirements
PDF upload and text extraction (PyMuPDF, Tesseract fallback); real provider-backed structured extraction; schema validation and uncertainty reporting; vendor/PO/GRN retrieval; deterministic multi-line matching; duplicate detection; evidence-backed exception investigation; structured recommendation; durable events and resumable human review; offline/live evaluation; developer console; health, tests, CI and Docker.

## Architecture
Modular monolith:
1. FastAPI transport and validation.
2. Pydantic domain/input/output schemas.
3. SQLAlchemy persistence and Alembic migrations.
4. PDF ingestion and provider adapter.
5. Typed application tools (no direct LLM database access).
6. Pure deterministic matching engine.
7. One LangGraph workflow with explicit state and human interrupt.
8. Evaluation package independent of UI.
9. Streamlit console calling HTTP APIs only.
10. Structured logs/events; optional Langfuse and OpenTelemetry exporters.

## Agent workflow
Receive persisted invoice/document reference -> extract -> validate -> resolve vendor -> retrieve PO and GRN -> deterministic match -> investigate with allow-listed tools -> verify evidence against stored records -> validate recommendation -> persist run/events -> interrupt for human review -> authorize a human decision and resume. No payment operation exists.

## Tool responsibilities
get_invoice, find_vendor, find_purchase_order, get_goods_receipt, get_vendor_history, get_financial_policy, run_three_way_match, get_supporting_evidence, create_exception_case. Tools validate arguments and call application services/repositories. The model receives tool schemas, never DB sessions, credentials or arbitrary code execution.

## Data model
Vendors have unique external codes; purchase orders belong to vendors and have line items; goods receipts reference POs and have received lines; invoices have unique vendor/invoice identifiers, lines and source-document metadata; policies define currency/tolerances; exception cases reference invoices and matching output; agent runs own events/checkpoints; evaluation runs own results. Use foreign keys, uniqueness and decimal monetary columns.

## PDF and extraction
Validate size/type, persist a safe document reference, extract text with PyMuPDF, use Tesseract only when text extraction is insufficient and the binary is installed, call a configured real LLM provider for structured extraction, validate with Pydantic and report missing/uncertain fields. Missing credentials or OCR dependencies are explicit errors, never successful fallback output.

## Matching and financial policy
Use Decimal arithmetic and explicit currency/tax/quantity/price tolerances. Compare vendor, PO, GRN, line quantities, unit prices, subtotal, tax and total; detect duplicate invoice identifiers. Ambiguous line mapping or missing source records must hold/escalate rather than approve. The example INV-1042 must produce a ₹50,000 pre-tax price variance and HOLD_FOR_REVIEW.

## Evaluation
Ground truth is stored separately from agent-visible records. Deterministic evaluators score extraction, matching, decision correctness, grounded evidence, tool use and safety. LLM-dependent runs require the configured provider and are BLOCKED when credentials are absent. No synthetic scores or mock traces. Dataset and prompt/agent versions are recorded.

## Observability and security
Persist run events with case/invoice/run/trace identifiers, node/tool, timestamp, status, duration and sanitized metadata. Langfuse is optional and only reports traces when configured. Logs exclude secrets and unnecessary invoice content. Treat PDF text as untrusted data; tools are allow-listed; recommendations are not approvals; only an authenticated/authorized human may decide.

## API surface
Expected endpoints: health/readiness; vendor/PO/GRN/policy CRUD or seed/import; invoice PDF upload and invoice retrieval; agent run start/status/events/SSE; case list/detail; human decision/resume; evaluation start/status/results/report. Exact implemented routes are listed below and in the OpenAPI schema.

## Technology choices
Python, FastAPI, Pydantic, SQLAlchemy, PostgreSQL, Alembic, LangGraph, provider-swappable LLM API, PyMuPDF, optional Tesseract, pytest, Streamlit, Docker Compose and GitHub Actions. Keep one deployable process initially; no microservices, Kubernetes, Kafka, Redis or vector database absent measured need.

## Configuration
Documented in .env.example. Secrets must remain local/environment-injected and must not be committed. Database URL, LLM provider/model/API key, upload limits, OCR binary, optional Langfuse and OTEL settings are configurable.

## Repository structure
The initial repository was empty. The intended layout is app/api, app/core, app/db, app/domain, app/ingestion, app/llm, app/tools, app/agent, app/evaluation, console, migrations, tests, scripts and .github/workflows. This section must be reconciled with the actual tree after implementation.

## Setup and operations
Use Python virtual environment, install requirements, copy .env.example to .env, start PostgreSQL, run Alembic migrations, start uvicorn and Streamlit. Exact verified commands belong in TESTING_GUIDE.md. Docker Compose is the alternative local path.

## Testing strategy
Separate pure unit tests, PostgreSQL integration tests, real-provider tests and optional tracing-service tests. Integration tests use an actual disposable PostgreSQL database. LLM tests call the configured provider. Missing services are reported BLOCKED/NOT RUN, not mocked or silently skipped.

## Deployment
Single API/worker-capable application and PostgreSQL. Streamlit is an internal console. CI runs formatting/linting, unit tests and deterministic quality gates; paid live LLM evaluations are manually triggered.

## Architectural decisions / exclusions
- Decimal and deterministic Python own financial calculations.
- One graph owns orchestration; no multi-agent hierarchy.
- LLM tools are typed allow-listed application functions.
- No payment authorization/execution or bank-detail mutation.
- No mandatory external tracing/evaluation SaaS.
- No mock LLM, fake trace, simulated tool or placeholder success path.

## Actual implementation status
- Repository inspection: **complete**; GitHub reported an empty repository (size 0), no README/files, and commit-history request returned 409 because there are no commits.
- Documentation bootstrap: **in progress**.
- Application components: **not started at document creation**. Update this section only after code is committed and verified.
- Tests: **not run** until a runnable implementation and execution environment exist.

## Known limitations / unresolved issues
The remote GitHub connector can edit repository contents but does not provide a local Windows runtime, PostgreSQL service or user API credentials. Tests requiring those resources must be run locally and reported honestly. Initial implementation scope may be constrained by available execution tools.

## Next steps
1. Establish project documents and actual repository scaffold.
2. Implement deterministic matching and database foundation.
3. Add real extraction/provider adapter and typed tools.
4. Add graph, human review, events and API.
5. Add evaluations, console, tests, Docker and CI.
6. Reconcile all status and commands with actual committed code.
