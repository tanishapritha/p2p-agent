from pathlib import Path
from uuid import uuid4
from fastapi import FastAPI, Depends, UploadFile, File, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import select
from pydantic import ValidationError
from app.config import settings
from app.db import get_db
from app.models import Invoice, ExceptionCase
from app.matching import MatchInput, run_three_way_match
from app.ingestion import extract_pdf_text, PDFIngestionError
from app.llm import extract_invoice_with_llm, LLMNotConfigured
from app.schemas import ExtractedInvoice

app = FastAPI(title="P2P Invoice Exception Agent", version="0.1.0")

@app.get("/health")
def health():
    return {"status":"ok", "llm_configured":bool(settings.llm_api_key)}

@app.post("/invoices/upload")
async def upload_invoice(file: UploadFile = File(...)):
    if file.content_type != "application/pdf" or not (file.filename or "").lower().endswith(".pdf"):
        raise HTTPException(415, "Only PDF invoices are accepted.")
    raw = await file.read(settings.max_upload_mb * 1024 * 1024 + 1)
    if len(raw) > settings.max_upload_mb * 1024 * 1024:
        raise HTTPException(413, "PDF exceeds configured upload limit.")
    target_dir = Path(settings.upload_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"{uuid4().hex}.pdf"
    target.write_bytes(raw)
    try:
        text, method = extract_pdf_text(str(target))
        extracted = await extract_invoice_with_llm(text)
        usage, model = extracted.pop("_usage", {}), extracted.pop("_model", settings.llm_model)
        validated = ExtractedInvoice.model_validate(extracted)
    except PDFIngestionError as exc:
        target.unlink(missing_ok=True)
        raise HTTPException(422, str(exc)) from exc
    except LLMNotConfigured as exc:
        target.unlink(missing_ok=True)
        raise HTTPException(503, str(exc)) from exc
    except ValidationError as exc:
        target.unlink(missing_ok=True)
        raise HTTPException(502, "LLM returned data that failed invoice schema validation.") from exc
    except Exception as exc:
        target.unlink(missing_ok=True)
        raise HTTPException(502, f"Extraction failed: {type(exc).__name__}") from exc
    # Extraction is deliberately not persisted as a trusted invoice until vendor resolution/review.
    target.unlink(missing_ok=True)
    return {"status":"EXTRACTED_NOT_PERSISTED", "source":method, "model":model,
            "usage":usage, "fields":validated.model_dump(mode="json"),
            "note":"Extraction is untrusted until reviewed and linked to verified business records."}

@app.post("/matching/evaluate")
def evaluate_match(payload: MatchInput):
    return run_three_way_match(payload)

@app.get("/invoices")
def list_invoices(db: Session = Depends(get_db)):
    return [{"id":i.id,"invoice_number":i.invoice_number,"currency":i.currency,"total":str(i.total)}
            for i in db.scalars(select(Invoice)).all()]

@app.get("/cases")
def list_cases(db: Session = Depends(get_db)):
    return [{"id":c.id,"invoice_id":c.invoice_id,"recommendation":c.recommendation,"result":c.result}
            for c in db.scalars(select(ExceptionCase)).all()]

@app.get("/ready")
def readiness(db: Session = Depends(get_db)):
    try:
        db.execute(select(1))
        return {"status":"ready","database":"connected","llm_configured":bool(settings.llm_api_key)}
    except Exception as exc:
        raise HTTPException(503, "Database unavailable") from exc
