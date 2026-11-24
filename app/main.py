from pathlib import Path
from uuid import uuid4
from fastapi import FastAPI, Depends, UploadFile, File, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import select
from pydantic import ValidationError, BaseModel, Field
from app.config import settings
from app.db import get_db
from app.models import Invoice, ExceptionCase
from app.matching import MatchInput, run_three_way_match
from app.ingestion import extract_pdf_text, PDFIngestionError
from app.llm import extract_invoice_with_llm, LLMNotConfigured
from app.schemas import ExtractedInvoice
from app.models import AgentRun, AgentEvent, Vendor, Invoice, InvoiceLine, PurchaseOrder, POLine, GoodsReceipt, GRNLine
from app.agent import run_invoice_agent
from datetime import datetime, timezone
from decimal import Decimal

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



class VendorCreate(BaseModel):
    code: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=255)

class MasterLine(BaseModel):
    description: str = Field(min_length=1, max_length=255)
    quantity: Decimal = Field(gt=Decimal("0"))
    unit_price: Decimal = Field(ge=Decimal("0"))

class POCreate(BaseModel):
    po_number: str = Field(min_length=1, max_length=64)
    vendor_id: int = Field(gt=0)
    currency: str = Field(default="INR", min_length=3, max_length=3)
    lines: list[MasterLine] = Field(min_length=1)

class GRNLineInput(BaseModel):
    description: str = Field(min_length=1, max_length=255)
    quantity: Decimal = Field(gt=Decimal("0"))

class GRNCreate(BaseModel):
    grn_number: str = Field(min_length=1, max_length=64)
    po_number: str = Field(min_length=1, max_length=64)
    lines: list[GRNLineInput] = Field(min_length=1)

def _require_local_master_data():
    if settings.app_env.lower() != "development":
        raise HTTPException(403,"Master-data entry API is disabled outside APP_ENV=development")

@app.post("/master-data/vendors")
def create_vendor(payload: VendorCreate, db: Session = Depends(get_db)):
    _require_local_master_data()
    if db.scalar(select(Vendor.id).where(Vendor.code==payload.code)):
        raise HTTPException(409,"Vendor code already exists")
    vendor=Vendor(code=payload.code,name=payload.name)
    db.add(vendor);db.commit();db.refresh(vendor)
    return {"id":vendor.id,"code":vendor.code,"name":vendor.name}

@app.post("/master-data/purchase-orders")
def create_purchase_order(payload: POCreate, db: Session = Depends(get_db)):
    _require_local_master_data()
    if not db.get(Vendor,payload.vendor_id):
        raise HTTPException(404,"Vendor ID does not exist")
    if db.scalar(select(PurchaseOrder.id).where(PurchaseOrder.po_number==payload.po_number)):
        raise HTTPException(409,"PO number already exists")
    po=PurchaseOrder(po_number=payload.po_number,vendor_id=payload.vendor_id,currency=payload.currency.upper(),
        lines=[POLine(description=line.description,quantity=line.quantity,unit_price=line.unit_price) for line in payload.lines])
    db.add(po);db.commit();db.refresh(po)
    return {"id":po.id,"po_number":po.po_number,"vendor_id":po.vendor_id}

@app.post("/master-data/goods-receipts")
def create_goods_receipt(payload: GRNCreate, db: Session = Depends(get_db)):
    _require_local_master_data()
    po=db.scalar(select(PurchaseOrder).where(PurchaseOrder.po_number==payload.po_number))
    if not po:
        raise HTTPException(404,"PO number not found")
    if db.scalar(select(GoodsReceipt.id).where(GoodsReceipt.grn_number==payload.grn_number)):
        raise HTTPException(409,"GRN number already exists")
    grn=GoodsReceipt(po_id=po.id,grn_number=payload.grn_number,
        lines=[GRNLine(description=line.description,quantity_received=line.quantity) for line in payload.lines])
    db.add(grn);db.commit();db.refresh(grn)
    return {"id":grn.id,"grn_number":grn.grn_number,"po_number":payload.po_number}

class ConfirmInvoiceRequest(ExtractedInvoice):
    vendor_id: int = Field(gt=0)
    confirmed_by: str = Field(min_length=2, max_length=255)

@app.post("/invoices/confirm")
def confirm_extracted_invoice(payload: ConfirmInvoiceRequest, db: Session = Depends(get_db)):
    """Persist extracted invoice facts only after a named human confirms and selects a vendor."""
    vendor=db.get(Vendor,payload.vendor_id)
    if not vendor:
        raise HTTPException(404,"Vendor ID does not exist")
    duplicate=db.scalar(select(Invoice.id).where(Invoice.vendor_id==vendor.id,
        Invoice.invoice_number==payload.invoice_number))
    if duplicate:
        raise HTTPException(409,"Invoice already exists for this vendor and number")
    invoice=Invoice(invoice_number=payload.invoice_number,vendor_id=vendor.id,
        po_number=payload.po_number,grn_number=payload.grn_number,currency=payload.currency.upper(),
        subtotal=payload.subtotal,tax=payload.tax,total=payload.total,
        extraction=payload.model_dump(mode="json"))
    invoice.lines=[InvoiceLine(description=line.description,quantity=line.quantity,unit_price=line.unit_price)
        for line in payload.line_items]
    db.add(invoice)
    try:
        db.commit()
    except Exception as exc:
        db.rollback()
        raise HTTPException(409,"Invoice persistence conflict; check duplicate or database constraints") from exc
    db.refresh(invoice)
    return {"status":"PERSISTED_PENDING_MATCH","invoice_id":invoice.id,"invoice_number":invoice.invoice_number,
        "vendor_id":vendor.id,"confirmed_by":payload.confirmed_by,
        "message":"Invoice stored. Run the exception agent to resolve linked PO and GRN. Human identity is not authenticated by this endpoint."}

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

class ReviewRequest(BaseModel):
    reviewer: str = Field(min_length=2, max_length=255)
    decision: str = Field(pattern="^(ACKNOWLEDGE|DISPUTE)$")
    note: str = Field(default="", max_length=2000)

@app.post("/agent/invoices/{invoice_id}/run")
def start_agent(invoice_id: int, idempotency_key: str | None = None):
    try:
        return run_invoice_agent(invoice_id, idempotency_key)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc

@app.get("/agent/runs/{run_id}")
def get_agent_run(run_id: int, db: Session = Depends(get_db)):
    run = db.get(AgentRun, run_id)
    if not run:
        raise HTTPException(404, "Agent run not found")
    events = db.scalars(select(AgentEvent).where(AgentEvent.run_id == run_id).order_by(AgentEvent.id)).all()
    return {"run_id":run.id,"invoice_id":run.invoice_id,"status":run.status,"state":run.state_json,
            "result":run.result_json,"reviewer":run.reviewer,"review_note":run.review_note,
            "events":[{"id":e.id,"type":e.event_type,"status":e.status,"details":e.metadata_json,
                      "created_at":e.created_at.isoformat() if e.created_at else None} for e in events]}

@app.post("/agent/runs/{run_id}/review")
def review_agent_run(run_id: int, payload: ReviewRequest, db: Session = Depends(get_db)):
    run=db.get(AgentRun,run_id)
    if not run:
        raise HTTPException(404,"Agent run not found")
    if run.status != "AWAITING_HUMAN_REVIEW":
        raise HTTPException(409,"Run is not waiting for human review")
    result=run.result_json or {}
    result["human_review"]={"decision":payload.decision,"reviewer":payload.reviewer,
                            "note":payload.note,"reviewed_at":datetime.now(timezone.utc).isoformat()}
    result["payment_execution"]=False
    run.result_json=result
    run.status="HUMAN_REVIEWED"
    run.reviewer=payload.reviewer
    run.review_note=payload.note
    db.add(AgentEvent(run_id=run_id,event_type="human_review",status=payload.decision,
                       metadata_json={"reviewer":payload.reviewer,"note":payload.note}))
    db.commit()
    return {"run_id":run_id,"status":run.status,"decision":payload.decision,
            "payment_execution":False,"message":"Review recorded. This endpoint cannot authorize or execute payment."}
