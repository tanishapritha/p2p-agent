"""Allow-listed P2P data tools. All reads go through the application DB session."""
from sqlalchemy import select, func
from sqlalchemy.orm import Session, selectinload
from app.models import (Invoice, Vendor, PurchaseOrder, GoodsReceipt, FinancialPolicy,
                        ExceptionCase, AgentRun)

class ToolNotFound(LookupError):
    pass

def get_invoice(db: Session, invoice_id: int) -> Invoice:
    obj = db.scalar(select(Invoice).options(selectinload(Invoice.lines)).where(Invoice.id == invoice_id))
    if obj is None:
        raise ToolNotFound(f"Invoice {invoice_id} not found")
    return obj

def find_vendor(db: Session, code: str | None = None, name: str | None = None) -> Vendor | None:
    if not code and not name:
        raise ValueError("Provide vendor code or name")
    stmt = select(Vendor)
    if code:
        stmt = stmt.where(Vendor.code == code)
    else:
        stmt = stmt.where(func.lower(Vendor.name) == name.strip().lower())
    return db.scalar(stmt)

def find_purchase_order(db: Session, po_number: str) -> PurchaseOrder | None:
    return db.scalar(select(PurchaseOrder).options(selectinload(PurchaseOrder.lines))
                     .where(PurchaseOrder.po_number == po_number))

def get_goods_receipt(db: Session, grn_number: str) -> GoodsReceipt | None:
    return db.scalar(select(GoodsReceipt).options(selectinload(GoodsReceipt.lines))
                     .where(GoodsReceipt.grn_number == grn_number))

def get_vendor_history(db: Session, vendor_id: int) -> dict:
    invoices = db.scalars(select(Invoice).where(Invoice.vendor_id == vendor_id)).all()
    cases = db.scalars(select(ExceptionCase).join(Invoice).where(Invoice.vendor_id == vendor_id)).all()
    return {"invoice_count": len(invoices), "case_count": len(cases),
            "invoice_ids": [i.id for i in invoices]}

def get_financial_policy(db: Session, name: str = "default") -> FinancialPolicy:
    policy = db.scalar(select(FinancialPolicy).where(FinancialPolicy.name == name))
    if policy is None:
        raise ToolNotFound(f"Financial policy '{name}' not found")
    return policy

def run_three_way_match_tool(payload):
    from app.matching import run_three_way_match
    return run_three_way_match(payload)

def get_supporting_evidence(db: Session, invoice_id: int) -> dict:
    invoice = get_invoice(db, invoice_id)
    po = find_purchase_order(db, invoice.po_number) if invoice.po_number else None
    grn = get_goods_receipt(db, invoice.grn_number) if invoice.grn_number else None
    return {"invoice_number": invoice.invoice_number, "vendor_id": invoice.vendor_id,
            "po_number": po.po_number if po else None, "grn_number": grn.grn_number if grn else None}

def create_exception_case(db: Session, invoice_id: int, result: dict) -> ExceptionCase:
    if result.get("recommendation") not in {"APPROVE_FOR_REVIEW", "HOLD_FOR_REVIEW", "REJECT_OR_ESCALATE"}:
        raise ValueError("Invalid recommendation")
    if result.get("payment_execution") is not False:
        raise ValueError("Payment execution is prohibited")
    existing = db.scalar(select(ExceptionCase).where(ExceptionCase.invoice_id == invoice_id))
    if existing:
        existing.result = result
        existing.recommendation = result["recommendation"]
        db.commit()
        db.refresh(existing)
        return existing
    case = ExceptionCase(invoice_id=invoice_id, recommendation=result["recommendation"], result=result)
    db.add(case)
    db.commit()
    db.refresh(case)
    return case
