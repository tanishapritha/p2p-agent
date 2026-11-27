from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ExtractedLine(BaseModel):
    model_config = ConfigDict(extra="forbid")
    description: str = Field(min_length=1, max_length=255)
    quantity: Decimal = Field(gt=0)
    unit_price: Decimal = Field(ge=0)


class ExtractedInvoice(BaseModel):
    model_config = ConfigDict(extra="forbid")
    invoice_number: str = Field(min_length=1, max_length=64)
    vendor_name: str = Field(min_length=1, max_length=255)
    po_number: str | None = None
    grn_number: str | None = None
    currency: str = Field(min_length=3, max_length=3)
    subtotal: Decimal = Field(ge=0)
    tax: Decimal = Field(ge=0)
    total: Decimal = Field(ge=0)
    line_items: list[ExtractedLine] = Field(min_length=1)
    missing_fields: list[str] = Field(default_factory=list)
    uncertainties: list[str] = Field(default_factory=list)

    @field_validator("currency")
    @classmethod
    def currency_uppercase(cls, value: str) -> str:
        return value.upper()
