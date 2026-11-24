from datetime import datetime, timezone
from decimal import Decimal
from sqlalchemy import String, DateTime, ForeignKey, Numeric, Text, UniqueConstraint, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db import Base

def now_utc():
    return datetime.now(timezone.utc)

class Vendor(Base):
    __tablename__ = "vendors"
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255))
    invoices: Mapped[list["Invoice"]] = relationship(back_populates="vendor")

class PurchaseOrder(Base):
    __tablename__ = "purchase_orders"
    id: Mapped[int] = mapped_column(primary_key=True)
    po_number: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    vendor_id: Mapped[int] = mapped_column(ForeignKey("vendors.id"))
    currency: Mapped[str] = mapped_column(String(3), default="INR")
    lines: Mapped[list["POLine"]] = relationship(cascade="all, delete-orphan")

class POLine(Base):
    __tablename__ = "po_lines"
    id: Mapped[int] = mapped_column(primary_key=True)
    po_id: Mapped[int] = mapped_column(ForeignKey("purchase_orders.id"))
    description: Mapped[str] = mapped_column(String(255))
    quantity: Mapped[Decimal] = mapped_column(Numeric(14, 3))
    unit_price: Mapped[Decimal] = mapped_column(Numeric(14, 2))

class GoodsReceipt(Base):
    __tablename__ = "goods_receipts"
    id: Mapped[int] = mapped_column(primary_key=True)
    grn_number: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    po_id: Mapped[int] = mapped_column(ForeignKey("purchase_orders.id"))
    lines: Mapped[list["GRNLine"]] = relationship(cascade="all, delete-orphan")

class GRNLine(Base):
    __tablename__ = "grn_lines"
    id: Mapped[int] = mapped_column(primary_key=True)
    grn_id: Mapped[int] = mapped_column(ForeignKey("goods_receipts.id"))
    description: Mapped[str] = mapped_column(String(255))
    quantity_received: Mapped[Decimal] = mapped_column(Numeric(14, 3))

class Invoice(Base):
    __tablename__ = "invoices"
    __table_args__ = (UniqueConstraint("vendor_id", "invoice_number", name="uq_vendor_invoice"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    invoice_number: Mapped[str] = mapped_column(String(64), index=True)
    vendor_id: Mapped[int] = mapped_column(ForeignKey("vendors.id"))
    po_number: Mapped[str | None] = mapped_column(String(64), nullable=True)
    grn_number: Mapped[str | None] = mapped_column(String(64), nullable=True)
    currency: Mapped[str] = mapped_column(String(3), default="INR")
    subtotal: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    tax: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    total: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    source_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    extraction: Mapped[dict] = mapped_column(JSON, default=dict)
    vendor: Mapped[Vendor] = relationship(back_populates="invoices")
    lines: Mapped[list["InvoiceLine"]] = relationship(cascade="all, delete-orphan")

class InvoiceLine(Base):
    __tablename__ = "invoice_lines"
    id: Mapped[int] = mapped_column(primary_key=True)
    invoice_id: Mapped[int] = mapped_column(ForeignKey("invoices.id"))
    description: Mapped[str] = mapped_column(String(255))
    quantity: Mapped[Decimal] = mapped_column(Numeric(14, 3))
    unit_price: Mapped[Decimal] = mapped_column(Numeric(14, 2))

class FinancialPolicy(Base):
    __tablename__ = "financial_policies"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    quantity_tolerance: Mapped[Decimal] = mapped_column(Numeric(8, 3), default=Decimal("0"))
    price_tolerance: Mapped[Decimal] = mapped_column(Numeric(8, 2), default=Decimal("0"))
    currency: Mapped[str] = mapped_column(String(3), default="INR")

class ExceptionCase(Base):
    __tablename__ = "exception_cases"
    id: Mapped[int] = mapped_column(primary_key=True)
    invoice_id: Mapped[int] = mapped_column(ForeignKey("invoices.id"), unique=True)
    recommendation: Mapped[str] = mapped_column(String(32))
    result: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)

class AgentRun(Base):
    __tablename__ = "agent_runs"
    id: Mapped[int] = mapped_column(primary_key=True)
    invoice_id: Mapped[int] = mapped_column(ForeignKey("invoices.id"))
    status: Mapped[str] = mapped_column(String(32), default="PENDING")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)

class AgentEvent(Base):
    __tablename__ = "agent_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("agent_runs.id"))
    event_type: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(32))
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)

class EvaluationRun(Base):
    __tablename__ = "evaluation_runs"
    id: Mapped[int] = mapped_column(primary_key=True)
    dataset_version: Mapped[str] = mapped_column(String(64))
    mode: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
