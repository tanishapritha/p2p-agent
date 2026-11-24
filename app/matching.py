from decimal import Decimal
from typing import Any
from pydantic import BaseModel, Field

class MatchLine(BaseModel):
    description: str
    quantity: Decimal
    unit_price: Decimal

class MatchInput(BaseModel):
    invoice_number: str
    vendor_match: bool
    currency: str = "INR"
    invoice_subtotal: Decimal
    invoice_tax: Decimal = Decimal("0")
    invoice_total: Decimal
    invoice_lines: list[MatchLine]
    po_found: bool
    po_currency: str | None = None
    po_lines: list[MatchLine] = Field(default_factory=list)
    grn_found: bool
    grn_lines: list[MatchLine] = Field(default_factory=list)
    duplicate: bool = False
    quantity_tolerance: Decimal = Decimal("0")
    price_tolerance: Decimal = Decimal("0")

def _money(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"))

def run_three_way_match(data: MatchInput) -> dict[str, Any]:
    """Deterministic match. Ambiguous/missing records never become approvals."""
    exceptions: list[dict[str, Any]] = []
    if data.duplicate:
        exceptions.append({"type": "DUPLICATE_INVOICE"})
    if not data.vendor_match:
        exceptions.append({"type": "VENDOR_MISMATCH"})
    if not data.po_found:
        exceptions.append({"type": "MISSING_PO"})
    if not data.grn_found:
        exceptions.append({"type": "MISSING_GRN"})
    if data.po_found and data.po_currency and data.currency != data.po_currency:
        exceptions.append({"type": "CURRENCY_MISMATCH"})
    quantity_status = "NOT_CHECKED"
    price_status = "NOT_CHECKED"
    if data.po_found and data.po_lines:
        if len(data.invoice_lines) != len(data.po_lines):
            exceptions.append({"type": "LINE_COUNT_MISMATCH"})
        else:
            qty_ok, price_ok = True, True
            for inv, po in zip(data.invoice_lines, data.po_lines):
                if inv.description.casefold().strip() != po.description.casefold().strip():
                    exceptions.append({"type": "AMBIGUOUS_DESCRIPTION", "invoice": inv.description, "po": po.description})
                    qty_ok = price_ok = False
                    continue
                if abs(inv.quantity - po.quantity) > data.quantity_tolerance:
                    qty_ok = False
                    exceptions.append({"type": "QUANTITY_MISMATCH", "description": inv.description,
                                       "invoice_quantity": str(inv.quantity), "po_quantity": str(po.quantity)})
                if abs(inv.unit_price - po.unit_price) > data.price_tolerance:
                    price_ok = False
                    delta = _money((inv.unit_price - po.unit_price) * inv.quantity)
                    exceptions.append({"type": "PRICE_MISMATCH", "description": inv.description,
                                       "invoice_amount": str(_money(inv.unit_price * inv.quantity)),
                                       "po_amount": str(_money(po.unit_price * inv.quantity)),
                                       "difference": str(delta)})
            quantity_status = "MATCH" if qty_ok else "MISMATCH"
            price_status = "MATCH" if price_ok else "MISMATCH"
    if data.grn_found and data.grn_lines:
        for inv in data.invoice_lines:
            received = sum((g.quantity for g in data.grn_lines
                            if g.description.casefold().strip() == inv.description.casefold().strip()), Decimal("0"))
            if received < inv.quantity - data.quantity_tolerance:
                exceptions.append({"type": "QUANTITY_NOT_RECEIVED", "description": inv.description,
                                   "invoice_quantity": str(inv.quantity), "received_quantity": str(received)})
    computed_subtotal = _money(sum((l.quantity * l.unit_price for l in data.invoice_lines), Decimal("0")))
    if computed_subtotal != _money(data.invoice_subtotal):
        exceptions.append({"type": "SUBTOTAL_MISMATCH", "computed": str(computed_subtotal),
                           "invoice": str(_money(data.invoice_subtotal))})
    if _money(data.invoice_subtotal + data.invoice_tax) != _money(data.invoice_total):
        exceptions.append({"type": "TOTAL_MISMATCH"})
    recommendation = "APPROVE_FOR_REVIEW" if not exceptions else "HOLD_FOR_REVIEW"
    return {"invoice_id": data.invoice_number, "vendor_status": "MATCHED" if data.vendor_match else "MISMATCH",
            "po_status": "FOUND" if data.po_found else "MISSING", "grn_status": "FOUND" if data.grn_found else "MISSING",
            "matching": {"quantity": quantity_status, "price": price_status}, "exceptions": exceptions,
            "recommendation": recommendation, "payment_execution": False}
