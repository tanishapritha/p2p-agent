"""LangGraph invoice exception workflow; financial outcomes remain deterministic.

LLM is not allowed to alter matching facts or issue payment instructions. Agent runs and
step events are persisted in the application database for audit and retrieval.
"""

from decimal import Decimal
from typing import Any, TypedDict

from langgraph.graph import END, StateGraph
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.db import SessionLocal
from app.matching import MatchInput, MatchLine, run_three_way_match
from app.models import AgentEvent, AgentRun, FinancialPolicy, GoodsReceipt, Invoice, PurchaseOrder
from app.telemetry import get_langchain_callbacks, observe_step, propagate_trace_context


class WorkflowState(TypedDict, total=False):
    run_id: int
    invoice_id: int
    status: str
    evidence: dict[str, Any]
    match_result: dict[str, Any]
    result: dict[str, Any]
    error: str


def _event(db, run_id: int, event_type: str, status: str, details: dict | None = None):
    db.add(
        AgentEvent(run_id=run_id, event_type=event_type, status=status, metadata_json=details or {})
    )
    db.commit()


def resolve_records(state: WorkflowState) -> WorkflowState:
    db = SessionLocal()
    try:
        with observe_step(
            "vendor_po_grn_retrieval",
            as_type="retriever",
            metadata={"agent_run_id": state.get("run_id"), "invoice_id": state.get("invoice_id")},
        ) as obs:
            inv = db.scalar(
                select(Invoice)
                .options(selectinload(Invoice.lines))
                .where(Invoice.id == state["invoice_id"])
            )
            if not inv:
                raise ValueError("Invoice not found")
            po = (
                db.scalar(
                    select(PurchaseOrder)
                    .options(selectinload(PurchaseOrder.lines))
                    .where(PurchaseOrder.po_number == inv.po_number)
                )
                if inv.po_number
                else None
            )
            grn = (
                db.scalar(
                    select(GoodsReceipt)
                    .options(selectinload(GoodsReceipt.lines))
                    .where(GoodsReceipt.grn_number == inv.grn_number)
                )
                if inv.grn_number
                else None
            )
            policy = db.scalar(select(FinancialPolicy).where(FinancialPolicy.name == "default"))
            evidence = {
                "invoice": {
                    "id": inv.id,
                    "number": inv.invoice_number,
                    "vendor_id": inv.vendor_id,
                    "currency": inv.currency,
                    "subtotal": str(inv.subtotal),
                    "tax": str(inv.tax),
                    "total": str(inv.total),
                    "lines": [
                        {
                            "description": l.description,
                            "quantity": str(l.quantity),
                            "unit_price": str(l.unit_price),
                        }
                        for l in inv.lines
                    ],
                },
                "po": None
                if not po
                else {
                    "number": po.po_number,
                    "vendor_id": po.vendor_id,
                    "currency": po.currency,
                    "lines": [
                        {
                            "description": l.description,
                            "quantity": str(l.quantity),
                            "unit_price": str(l.unit_price),
                        }
                        for l in po.lines
                    ],
                },
                "grn": None
                if not grn
                else {
                    "number": grn.grn_number,
                    "po_id": grn.po_id,
                    "lines": [
                        {
                            "description": l.description,
                            "quantity": str(l.quantity),
                            "unit_price": "0",
                        }
                        for l in grn.lines
                    ],
                },
                "policy": {
                    "quantity_tolerance": str(policy.quantity_tolerance),
                    "price_tolerance": str(policy.price_tolerance),
                    "currency": policy.currency,
                }
                if policy
                else None,
                "duplicate": db.scalar(
                    select(Invoice.id).where(
                        Invoice.vendor_id == inv.vendor_id,
                        Invoice.invoice_number == inv.invoice_number,
                        Invoice.id != inv.id,
                    )
                )
                is not None,
                "relationships_valid": bool(
                    po and grn and po.vendor_id == inv.vendor_id and grn.po_id == po.id
                ),
            }
            state["evidence"] = evidence
            state["status"] = "RECORDS_RESOLVED"
            obs.update(
                metadata={
                    "agent_run_id": state.get("run_id"),
                    "po_found": bool(po),
                    "grn_found": bool(grn),
                    "relationships_valid": evidence["relationships_valid"],
                    "duplicate": evidence["duplicate"],
                    "status": "RECORDS_RESOLVED",
                }
            )
            _event(
                db,
                state["run_id"],
                "record_resolution",
                "SUCCEEDED",
                {
                    "po_found": bool(po),
                    "grn_found": bool(grn),
                    "relationship_valid": evidence["relationships_valid"],
                },
            )
            return state
    except Exception as exc:  # noqa: BLE001 - workflow node boundary must fail closed and record FAILED state
        state["status"] = "FAILED"
        state["error"] = str(exc)
        _event(db, state["run_id"], "record_resolution", "FAILED", {"error": type(exc).__name__})
        return state
    finally:
        db.close()


def deterministic_match(state: WorkflowState) -> WorkflowState:
    if state.get("status") == "FAILED":
        return state
    e = state["evidence"]
    inv = e["invoice"]
    po = e["po"]
    grn = e["grn"]
    policy = e["policy"]
    rel = e["relationships_valid"]
    try:
        payload = MatchInput(
            invoice_number=inv["number"],
            vendor_match=bool(po and po["vendor_id"] == inv["vendor_id"] and rel),
            currency=inv["currency"],
            invoice_subtotal=Decimal(inv["subtotal"]),
            invoice_tax=Decimal(inv["tax"]),
            invoice_total=Decimal(inv["total"]),
            invoice_lines=[MatchLine(**l) for l in inv["lines"]],
            po_found=bool(po and rel),
            po_currency=po["currency"] if po and rel else None,
            po_lines=[MatchLine(**l) for l in po["lines"]] if po and rel else [],
            grn_found=bool(grn and rel),
            grn_lines=[
                MatchLine(
                    description=l["description"],
                    quantity=Decimal(l["quantity"]),
                    unit_price=Decimal(0),
                )
                for l in grn["lines"]
            ]
            if grn and rel
            else [],
            duplicate=e["duplicate"],
            quantity_tolerance=Decimal(policy["quantity_tolerance"]) if policy else Decimal(0),
            price_tolerance=Decimal(policy["price_tolerance"]) if policy else Decimal(0),
        )
        with observe_step(
            "three_way_matching",
            as_type="evaluator",
            metadata={"agent_run_id": state.get("run_id")},
        ) as obs:
            result = run_three_way_match(payload)
            if not rel:
                result["exceptions"].append({"type": "INVALID_PO_GRN_VENDOR_RELATIONSHIP"})
                result["recommendation"] = "HOLD_FOR_REVIEW"
            obs.update(
                metadata={
                    "agent_run_id": state.get("run_id"),
                    "recommendation": result["recommendation"],
                    "exception_count": len(result["exceptions"]),
                    "exception_types": [e.get("type") for e in result["exceptions"]],
                    "status": "MATCHED",
                }
            )
        state["match_result"] = result
        state["status"] = "MATCHED"
        event_db = SessionLocal()
        try:
            _event(
                event_db,
                state["run_id"],
                "deterministic_match",
                "SUCCEEDED",
                {"exception_count": len(result["exceptions"])},
            )
        finally:
            event_db.close()
        return state
    except Exception as exc:  # noqa: BLE001 - workflow node boundary must fail closed and record FAILED state
        state["status"] = "FAILED"
        state["error"] = str(exc)
        return state


def recommendation(state: WorkflowState) -> WorkflowState:
    with observe_step(
        "final_recommendation",
        as_type="span",
        metadata={"agent_run_id": state.get("run_id")},
    ) as obs:
        if state.get("status") == "FAILED":
            state["result"] = {
                "status": "FAILED",
                "error": state.get("error"),
                "payment_execution": False,
            }
        else:
            outcome = state["match_result"]
            state["result"] = {
                "status": "AWAITING_HUMAN_REVIEW",
                "recommendation": outcome["recommendation"],
                "exceptions": outcome["exceptions"],
                "match": outcome,
                "evidence": state["evidence"],
                "payment_execution": False,
                "review_required": True,
            }
            state["status"] = "AWAITING_HUMAN_REVIEW"
        obs.update(
            metadata={
                "agent_run_id": state.get("run_id"),
                "status": state.get("status", "FAILED"),
                "recommendation": state.get("result", {}).get("recommendation"),
                "payment_execution": False,
            }
        )
        db = SessionLocal()
        try:
            run = db.get(AgentRun, state["run_id"])
            if run:
                run.status = state.get("status", "FAILED")
                run.state_json = {"step": "recommendation", "status": run.status}
                run.result_json = state.get("result", {})
                db.commit()
                _event(
                    db,
                    run.id,
                    "final_recommendation",
                    run.status,
                    {"recommendation": state.get("result", {}).get("recommendation")},
                )
        finally:
            db.close()
        return state


def build_graph():
    graph = StateGraph(WorkflowState)
    graph.add_node("resolve_records", resolve_records)
    graph.add_node("deterministic_match", deterministic_match)
    graph.add_node("recommendation", recommendation)
    graph.set_entry_point("resolve_records")
    graph.add_edge("resolve_records", "deterministic_match")
    graph.add_edge("deterministic_match", "recommendation")
    graph.add_edge("recommendation", END)
    return graph.compile()


invoice_exception_graph = build_graph()


def run_invoice_agent(invoice_id: int, idempotency_key: str | None = None) -> dict:
    db = SessionLocal()
    try:
        if idempotency_key:
            existing = db.scalar(
                select(AgentRun).where(AgentRun.idempotency_key == idempotency_key)
            )
            if existing:
                if existing.invoice_id != invoice_id:
                    raise ValueError("Idempotency key already used for a different invoice")
                return {
                    "run_id": existing.id,
                    "status": existing.status,
                    "result": existing.result_json,
                    "reused": True,
                }
        invoice = db.get(Invoice, invoice_id)
        if not invoice:
            raise ValueError("Invoice not found")
        run = AgentRun(
            invoice_id=invoice_id,
            status="RUNNING",
            idempotency_key=idempotency_key,
            state_json={"step": "started"},
            result_json={},
        )
        db.add(run)
        db.commit()
        db.refresh(run)
        _event(db, run.id, "run_started", "SUCCEEDED", {"invoice_id": invoice_id})
        run_id = run.id
    finally:
        db.close()
    with propagate_trace_context(
        agent_run_id=run_id,
        workflow_name="invoice_exception_workflow",
        metadata={"agent_run_id": str(run_id), "invoice_id": str(invoice_id)},
        tags=["p2p-agent", f"run:{run_id}"],
    ):
        callbacks = get_langchain_callbacks()
        invoke_config = {"callbacks": callbacks} if callbacks else {}
        state = invoice_exception_graph.invoke(
            {"run_id": run_id, "invoice_id": invoice_id, "status": "RUNNING"},
            config=invoke_config,
        )
    return {
        "run_id": run_id,
        "status": state.get("status"),
        "result": state.get("result", {}),
        "reused": False,
    }
