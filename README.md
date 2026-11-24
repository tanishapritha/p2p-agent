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
The initial implementation provides typed SQLAlchemy persistence, deterministic matching, PDF text/OCR extraction, a real OpenAI-compatible structured extraction call, API health and invoice/matching endpoints, and unit tests. LangGraph human-interrupt orchestration, Langfuse, evaluation datasets and a full run explorer remain explicitly incomplete until implemented and verified.
