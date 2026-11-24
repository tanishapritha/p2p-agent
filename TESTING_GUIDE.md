# Testing Guide — Windows PowerShell

This guide intentionally lists only commands and functionality that exist in the repository today. The full LangGraph agent, evaluation CLI, human approval/resume and trace explorer are not implemented; do not try to infer or simulate them.

## 1. Prerequisites
- Windows 10/11, Git, Python 3.11+, PostgreSQL 15+.
- Optional OCR: Tesseract installed and available on PATH (or set TESSERACT_CMD).
- A real OpenAI-compatible API key and model for PDF extraction.
- Docker Desktop only if using Compose.

## 2. Clone and environment
```powershell
git clone https://github.com/tanishapritha/p2p-agent.git
cd p2p-agent
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e ".[dev]"
Copy-Item .env.example .env
notepad .env
```
Set DATABASE_URL, LLM_API_KEY and LLM_MODEL as needed. LLM_BASE_URL defaults to the OpenAI API root. Never commit .env.

## 3. PostgreSQL and migrations
Create a local database/user matching DATABASE_URL. Start the PostgreSQL service (adjust service name/version):
```powershell
Get-Service *postgres*
Start-Service postgresql-x64-15
alembic upgrade head
```
The initial migration creates tables declared in app.models. Verify using psql or pgAdmin. Migration application has not been run by the repository author in this remote session.

## 4. Start the API
```powershell
uvicorn app.main:app --reload
```
Open http://127.0.0.1:8000/docs. Routes: GET /health, GET /ready, POST /invoices/upload, POST /invoices/confirm, POST /master-data/vendors, POST /master-data/purchase-orders, POST /master-data/goods-receipts, POST /matching/evaluate, GET /invoices, GET /cases, POST /agent/invoices/{invoice_id}/run, GET /agent/runs/{run_id}, POST /agent/runs/{run_id}/review. /ready requires PostgreSQL; /health only reports process and whether an LLM key is configured.

## 5. Start Streamlit
In another PowerShell terminal:
```powershell
.\.venv\Scripts\Activate.ps1
streamlit run console/app.py
```
Use the sidebar Backend URL. The console exposes PDF extraction, deterministic match and case listing. It is a small workbench, not the full requested developer console.

## 6. PDF ingestion and real extraction
Use a valid invoice PDF and POST it to /invoices/upload as multipart field file, or upload it in Streamlit. Text PDFs use PyMuPDF; scanned PDFs use Tesseract if installed. The endpoint calls the configured real LLM and validates its structured output. Missing LLM_API_KEY returns 503; provider failures return 502; invalid PDFs return 422. Successful extraction returns EXTRACTED_NOT_PERSISTED: no invoice/vendor is automatically created and the temporary PDF is removed. After reviewing the extracted JSON and selecting a verified vendor ID, send it to POST /invoices/confirm (include confirmed_by) to save the invoice. This API does not authenticate reviewer identity. This is deliberate until source-record review and persistence are implemented.

## 7. Test deterministic matching
Open POST /matching/evaluate in Swagger or send a JSON body. Example PowerShell:
```powershell
$body = @{
  invoice_number="INV-1042"; vendor_match=$true; currency="INR"
  invoice_subtotal="550000"; invoice_tax="99000"; invoice_total="649000"
  invoice_lines=@(@{description="laptop";quantity="10";unit_price="55000"})
  po_found=$true; po_currency="INR"
  po_lines=@(@{description="laptop";quantity="10";unit_price="50000"})
  grn_found=$true
  grn_lines=@(@{description="laptop";quantity="10";unit_price="0"})
} | ConvertTo-Json -Depth 8
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/matching/evaluate -ContentType "application/json" -Body $body
```
Expected: quantity MATCH, price MISMATCH, PRICE_MISMATCH difference 50000.00, recommendation HOLD_FOR_REVIEW. This route currently accepts caller-supplied found/match flags; it is not a substitute for DB-verified matching.

## 8. Local master-data entry
The API supports development-only vendor, PO and goods-receipt entry. These routes are blocked unless APP_ENV=development. No authentication exists; do not expose this application to a public network.
```powershell
$v = Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/master-data/vendors -ContentType "application/json" -Body (@{code="V001";name="Local Test Vendor"} | ConvertTo-Json)
$po = @{po_number="PO-LOCAL-1";vendor_id=$v.id;currency="INR";lines=@(@{description="paper";quantity="10";unit_price="100"})} | ConvertTo-Json -Depth 5
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/master-data/purchase-orders -ContentType "application/json" -Body $po
$grn = @{grn_number="GRN-LOCAL-1";po_number="PO-LOCAL-1";lines=@(@{description="paper";quantity="10"})} | ConvertTo-Json -Depth 5
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/master-data/goods-receipts -ContentType "application/json" -Body $grn
```
Use only clearly labeled local test business records, not production transactions.

## 9. Agent run / review flow
The graph resolves invoice, PO and GRN records using the invoice's stored references, verifies PO vendor and GRN-to-PO linkage, then calls the deterministic matcher. It persists agent run/event records and returns AWAITING_HUMAN_REVIEW. The workflow is LangGraph orchestration, but it is not yet checkpointed across process restarts and it does not perform LLM-driven tool investigation.

Example:
```powershell
Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8000/agent/invoices/1/run"
Invoke-RestMethod -Uri "http://127.0.0.1:8000/agent/runs/1"
$review = @{ reviewer="reviewer@example.local"; decision="ACKNOWLEDGE"; note="Reviewed match evidence." } | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8000/agent/runs/1/review" -ContentType "application/json" -Body $review
```
Review decisions are ACKNOWLEDGE or DISPUTE and only record review metadata. They are not payment authorization. Use an existing persisted invoice ID; the upload endpoint currently extracts but does not save invoices.

## 10. Offline matcher evaluation
The labeled synthetic dataset is explicitly a deterministic test/evaluation fixture, not production transaction data:
```powershell
python -m app.evaluate --dataset eval/datasets/matching_v1.jsonl
```
It reports case accuracy, hold recall, and false-approve count. Do not confuse matcher evaluation with full agent evaluation or live LLM quality.

## 11. Tools and database
Typed DB functions are in app/tools.py and accept a real SQLAlchemy Session. They are not yet exposed through API or registered with an LLM. Create business records manually only for local development; there is no seed dataset or CRUD API yet.

## 12. Tests actually available
Run the current no-credential deterministic tests:
```powershell
pytest tests/test_matching.py -q
```
There are four unit tests. No PostgreSQL integration, real-provider test, LangGraph behavior, security, E2E or trace tests currently exist. Do not run marker commands expecting nonexistent suites.

Quality check:
```powershell
ruff check .
```
The repository does not currently configure a formatter/type checker gate. Record exact output and exit code in IMPLEMENTATION_LOG.md. Tests have not been executed by the remote editing session.

## 13. Docker
Ensure .env exists first:
```powershell
docker compose up --build
docker compose logs -f
docker compose down
```
Compose starts PostgreSQL and the API. The database volume persists. Docker startup/migration behavior must be verified locally.

## 14. Not yet available
- LangGraph real agent run and tool-calling workflow.
- Human approval, authorization and checkpoint resume.
- Run/event history, SSE, Langfuse and OpenTelemetry traces.
- Offline/live evaluation CLI, synthetic dataset and quality gates.
- Dataset manager, experiments, full run explorer and system-health metrics.
- Authenticated APIs and production deployment controls.

## 15. Troubleshooting
- PostgreSQL connection refused: start the service and check DATABASE_URL.
- Alembic error: check database exists and DATABASE_URL points to the intended instance.
- LLM 401/403: verify key, provider URL, model access and quota.
- OCR fallback error: install Tesseract, pytesseract and Pillow; verify TESSERACT_CMD.
- Invalid output: provider output failed Pydantic validation; inspect provider/model compatibility.
- Upload rejected: file must be a PDF and within MAX_UPLOAD_MB.
- Do not substitute mocked LLM calls, fake database results or fabricated traces when a dependency is unavailable. Record BLOCKED/NOT RUN.
