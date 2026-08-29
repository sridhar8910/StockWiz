import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict

class OrderResponse(BaseModel):
    order_id: str
    user_id: str
    subscription_id: Optional[int] = None
    ticker: str
    action: str
    quantity: float
    status: str
    idempotency_key: Optional[str] = None
    timestamp: datetime.datetime

    model_config = ConfigDict(from_attributes=True)
