# Implementation Log

Status vocabulary: implemented (code exists), tested (executed with observed result), blocked, not started. Code presence is not evidence of runtime correctness.

| Area | Status | Files | Implemented / evidence | Tests actually executed | Remaining |
|---|---|---|---|---|---|
| Repository inspection | implemented | GitHub metadata | Empty repo, zero files, no commits initially; write permission confirmed. | Repository metadata and code search. | None. |
| Permanent docs | implemented | PROJECT_STATE.md, TESTING_GUIDE.md, IMPLEMENTATION_LOG.md | Created before application files; updated to describe actual state. | Not applicable. | Keep updated. |
| Foundation / config | implemented | pyproject.toml, .env.example, app/config.py, app/db.py | Settings, SQLAlchemy engine/session and dependencies. | NOT RUN. | Runtime verification. |
| DB schema / migration | implemented | app/models.py, alembic.ini, migrations/ | Vendor, PO, GRN, invoice, policy, case, run/event/evaluation-run models; initial metadata migration. | NOT RUN; no PostgreSQL available to this editing session. | Apply migration and add schema tests. |
| PDF / LLM extraction | implemented, partial | app/ingestion.py, app/llm.py, app/schemas.py, app/main.py | PyMuPDF, Tesseract fallback, real OpenAI-compatible JSON-schema request, Pydantic validation. Extracted result is not persisted. | NOT RUN; no credentials or runtime. | Live-provider tests, OCR test, persistence/review workflow. |
| Deterministic matching | implemented, partial | app/matching.py | Decimal matching, quantity/price, GRN received, currency, totals, vendor/duplicate flags; missing records fail closed. | NOT RUN. Four fixed unit tests committed. | DB-backed record resolution, tax policy and relationship checks. |
| P2P tools | implemented, partial | app/tools.py | Nine actual SQLAlchemy application functions. | NOT RUN. | Authorization, tool schema integration and DB tests. |
| FastAPI | implemented, partial | app/main.py | Health/readiness, upload, match, invoice list and case list. | NOT RUN. | CRUD, authentication, persistence workflow, API tests. |
| LangGraph / human review | not started | dependency only | No production graph, checkpoint or reviewer approval flow. | NOT RUN. | Implement durable interrupt/resume and authorization. |
| Events / traces | not started | AgentEvent model only | Event table exists; no event writer, SSE, Langfuse or OTel. | NOT RUN. | Event architecture and trace integration. |
| Evaluation | not started | EvaluationRun model only | No dataset, ground truth, CLI, evaluator or metrics. | NOT RUN. | Build deterministic and live evaluation engine. |
| Streamlit | implemented, partial | console/app.py | HTTP-backed PDF, match and case tabs. | NOT RUN. | Run explorer, evaluation, dataset, experiments, health. |
| Docker / CI | implemented, unverified | Dockerfile, docker-compose.yml, .github/workflows/ci.yml | Basic API image, PostgreSQL Compose and unit CI workflow. | NOT RUN; CI has not run. | Verify build and workflow; migration startup. |
| Tests | implemented, unverified | tests/test_matching.py | Four deterministic tests, no mocks. | NOT RUN in this session. | Add PostgreSQL, live provider and E2E suites. |

## Commits
- Documentation bootstrap: 5a0fe464f65ce74b444ef967f57bb7397164e7f4
- Documentation guide: de8ac984d0e6c3550172bebfa5f1566e3b59c4e3
- Implementation log: bb93719d3e28cff49860567eab220a256515d3ba
- Subsequent files were committed directly to main through the GitHub contents API (one file per commit). Latest commit at final inspection: 2ad2ec4969a88f96d10f987098ee9894060ea46b (fix: run database migrations in container startup). This is more granular than the preferred small number of commits; no history rewrite was attempted.

## Execution environment and test evidence
This work used the GitHub repository connector. It can inspect and commit repository files but does not provide a local shell, installed dependencies, PostgreSQL server, Docker daemon or user LLM credentials. Therefore no pytest, Ruff, Alembic, Docker or live LLM command was executed here. All such checks are **NOT RUN**, not passed. Live extraction is blocked until a real API key is configured.

## Next actions
1. Verify install, Ruff, pytest and Alembic locally.
2. Fix any runtime/type/schema issues discovered.
3. Add DB-backed invoice persistence and verified PO/GRN/vendor retrieval.
4. Implement LangGraph tool loop with durable checkpoints and authorized human review.
5. Add event/SSE/trace pipeline and real evaluation dataset/CLI.
6. Expand console and integration/live/E2E test coverage.
