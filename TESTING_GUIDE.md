# Testing Guide (Windows PowerShell)

This guide describes the repository's actual commands. Features marked unavailable below are not silently simulated; use the implementation status in PROJECT_STATE.md.

## 1. Prerequisites
- Windows 10/11, Git, Python 3.11+, PostgreSQL 15+.
- Optional: Tesseract OCR installed and on PATH.
- A real LLM provider API key for extraction and agent runs.
- Optional Langfuse credentials for external traces.

## 2. Environment
```powershell
git clone https://github.com/tanishapritha/p2p-agent.git
cd p2p-agent
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
```
Install dependencies using the repository's requirements file when present. Copy configuration:
```powershell
Copy-Item .env.example .env
notepad .env
```
Never commit .env. Set DATABASE_URL to your local PostgreSQL database and configure the provider key/model only for live LLM operations.

## 3. PostgreSQL and migrations
Create a database and user in PostgreSQL, then set DATABASE_URL in .env. Start the PostgreSQL Windows service from Services or:
```powershell
Get-Service *postgres*
Start-Service postgresql-x64-15
```
Use the installed service name if it differs. Run migrations with the repository's Alembic configuration:
```powershell
alembic upgrade head
```
If migrations are not yet present, do not substitute create_all and call it a migration; check PROJECT_STATE.md.

## 4. Backend
```powershell
uvicorn app.main:app --reload
```
Open http://127.0.0.1:8000/docs and call the health endpoint. Use the exact module path/routes in the current source if they differ.

## 5. Streamlit console
In a second PowerShell:
```powershell
.\.venv\Scripts\Activate.ps1
streamlit run console/app.py
```
Configure the console's backend URL if required. The console must call backend APIs; it must not implement financial calculations.

## 6. PDF ingestion
Upload a real invoice PDF using the documented upload endpoint or console. Text PDFs use PyMuPDF. Scanned PDFs require Tesseract. Extraction requires a configured real LLM provider. Confirm that the response identifies missing fields/uncertainty; malformed PDFs and missing credentials must return explicit failures, not fabricated data.

## 7. P2P tools and matching
Use the documented tool CLI/API entry points where implemented. Insert synthetic business records into the actual PostgreSQL database before matching. The canonical example is INV-1042: 10 laptops at ₹55,000 versus PO-204 at ₹50,000, with 10 received. Expected deterministic result: quantity match, ₹50,000 pre-tax price variance, HOLD_FOR_REVIEW. Never infer test success from this expected value; run the test command and inspect its output.

## 8. Real agent
Start a run through the agent API/console. It must use the configured provider and actual application tools. Missing provider credentials mean BLOCKED. Inspect persisted run events and the Langfuse trace only when Langfuse is configured.

## 9. Human review
Inspect the generated case, authenticate as an authorized reviewer, submit a decision and resume the checkpoint. Confirm an agent identity cannot approve its own recommendation and no payment endpoint exists.

## 10. Evaluations
Offline evaluation means no evaluation SaaS, not no LLM. It still calls the configured real provider and actual database/tools:
```powershell
python -m app.evaluation.cli --mode offline
```
Live evaluation:
```powershell
python -m app.evaluation.cli --mode live
```
Use only CLI options actually exposed by the installed version. If the provider key/database is missing, record BLOCKED; never use a mock provider.

## 11. Tests and quality checks
Run no-credential unit tests:
```powershell
pytest -m "not integration and not live"
```
PostgreSQL integration tests:
```powershell
$env:TEST_DATABASE_URL="postgresql+psycopg://user:password@localhost:5432/p2p_agent_test"
pytest -m integration
```
Real-provider tests:
```powershell
pytest -m live
```
Optional tracing tests require Langfuse credentials. Run:
```powershell
ruff check .
ruff format --check .
mypy app
```
Use the actual pyproject/pytest markers; do not interpret an uncollected marker as a passed test.

## 12. Docker
When Docker assets are present:
```powershell
docker compose up --build
docker compose logs -f
docker compose down
```
Persisted database volumes remain unless explicitly removed. Do not run destructive volume removal against data you need.

## 13. Expected results and troubleshooting
- Database connection refused: start PostgreSQL and verify DATABASE_URL/port.
- Migration error: inspect Alembic revision state and apply migrations in order.
- Provider authentication/rate limit: verify key, provider, model access and quota; live run is BLOCKED otherwise.
- Scanned PDF has no text: install Tesseract and configure its executable path.
- Invalid PDF: use a valid PDF; ingestion should report a validation error.
- No Langfuse trace: verify credentials and host; application events remain separately persisted.
- Integration tests unavailable: report NOT RUN/BLOCKED, not passed.
- Port conflict: change uvicorn/Streamlit port using their documented flags.

## 14. Honest test reporting
Record exact commands, exit codes and observed output in IMPLEMENTATION_LOG.md. Distinguish PASS, FAIL, BLOCKED and NOT RUN. Synthetic records are permitted test data; fake model responses, mocked DB integration and fabricated metrics are prohibited.
