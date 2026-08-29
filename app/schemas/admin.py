import re
from typing import Optional, Any
from pydantic import BaseModel, Field, field_validator
from app.schemas.folio import parse_folio_id

TICKER_REGEX = re.compile(r"^[A-Z0-9\-&]{1,20}$")

class RebalanceRequest(BaseModel):
    folio_id: Any = Field(..., description="Folio ID, can be integer or string like 'folio-1'")
    outgoing_ticker: str = Field(..., min_length=1, max_length=20, description="Ticker of the stock to be replaced")
    incoming_ticker: str = Field(..., min_length=1, max_length=20, description="Ticker of the new stock to be added")
    new_base_quantity: Optional[float] = Field(None, gt=0, description="Optional new base quantity for the incoming stock. Defaults to outgoing stock's base quantity if not specified.")

    @field_validator("folio_id", mode="before")
    @classmethod
    def validate_folio_id(cls, v: Any) -> int:
        return parse_folio_id(v)

    @field_validator("outgoing_ticker", "incoming_ticker")
    @classmethod
    def validate_and_normalize_ticker(cls, v: str) -> str:
        cleaned = v.strip().upper()
        if not TICKER_REGEX.match(cleaned):
            raise ValueError(f"Ticker '{v}' is invalid. Must be 1-20 alphanumeric characters, hyphens, or ampersands.")
        return cleaned
