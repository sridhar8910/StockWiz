from typing import Optional, Any, List
from pydantic import BaseModel, Field, field_validator, ConfigDict
from app.schemas.folio import parse_folio_id
from app.schemas.order import OrderResponse

class SubscriptionCreate(BaseModel):
    user_id: str = Field(..., min_length=1, description="Unique user identifier")
    folio_id: Any = Field(..., description="Folio ID, can be an integer or string like 'folio-1'")
    multiplier: float = Field(..., gt=0, description="Quantity multiplier, e.g. 1.0, 3.0, 5.0")

    @field_validator("user_id")
    @classmethod
    def validate_user_id(cls, v: str) -> str:
        cleaned = v.strip() if v else ""
        if not cleaned:
            raise ValueError("User ID cannot be empty or whitespace")
        return cleaned

    @field_validator("folio_id", mode="before")
    @classmethod
    def validate_folio_id(cls, v: Any) -> int:
        return parse_folio_id(v)

class SubscriptionResponse(BaseModel):
    id: int
    user_id: str
    folio_id: int
    multiplier: float
    active: bool
    status: str = "ACTIVE"
    folio_name: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)

class SubscriptionResult(BaseModel):
    subscription: SubscriptionResponse
    orders: List[OrderResponse]
