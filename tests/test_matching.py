from decimal import Decimal
from app.matching import MatchInput, MatchLine, run_three_way_match

def test_price_mismatch_holds_with_exact_variance():
    data = MatchInput(invoice_number="INV-1042", vendor_match=True, currency="INR",
        invoice_subtotal=Decimal("550000"), invoice_tax=Decimal("99000"), invoice_total=Decimal("649000"),
        invoice_lines=[MatchLine(description="laptop", quantity=10, unit_price=55000)],
        po_found=True, po_currency="INR",
        po_lines=[MatchLine(description="laptop", quantity=10, unit_price=50000)],
        grn_found=True, grn_lines=[MatchLine(description="laptop", quantity=10, unit_price=0)])
    result = run_three_way_match(data)
    assert result["matching"] == {"quantity":"MATCH","price":"MISMATCH"}
    assert result["recommendation"] == "HOLD_FOR_REVIEW"
    price = next(e for e in result["exceptions"] if e["type"] == "PRICE_MISMATCH")
    assert price["difference"] == "50000.00"
    assert result["payment_execution"] is False

def test_missing_po_never_approves():
    data = MatchInput(invoice_number="I-1", vendor_match=True, invoice_subtotal=10,
        invoice_total=10, invoice_lines=[MatchLine(description="x", quantity=1, unit_price=10)],
        po_found=False, grn_found=True)
    assert run_three_way_match(data)["recommendation"] == "HOLD_FOR_REVIEW"

def test_duplicate_and_vendor_mismatch_hold():
    data = MatchInput(invoice_number="I-2", vendor_match=False, invoice_subtotal=0,
        invoice_total=0, invoice_lines=[], po_found=True, grn_found=True, duplicate=True)
    result = run_three_way_match(data)
    assert result["recommendation"] == "HOLD_FOR_REVIEW"
    assert {e["type"] for e in result["exceptions"]} >= {"DUPLICATE_INVOICE","VENDOR_MISMATCH"}
