from typing import List, Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from app.db.database import get_db
from app.schemas.order import OrderResponse
from app.services.order_service import OrderService

router = APIRouter(prefix="/api/orders", tags=["Orders"])

@router.get("", response_model=List[OrderResponse])
def get_orders(
    user_id: Optional[str] = Query(None, description="Filter orders by User ID"),
    limit: int = Query(100, ge=1, le=1000, description="Limit the number of returned orders"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
    db: Session = Depends(get_db)
):
    """
    Retrieve execution receipts.
    """
    return OrderService.get_orders(db, user_id=user_id, limit=limit, offset=offset)
