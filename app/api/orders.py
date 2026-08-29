from typing import List, Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from app.db.database import get_db
from app.schemas.order import OrderResponse
from app.services.order_service import OrderService

router = APIRouter(prefix="/api/orders", tags=["Orders"])

@router.get(
    "",
    response_model=List[OrderResponse],
    summary="List Order Execution Receipts",
    description="Retrieve execution receipts recorded by the synthetic broker. Supports partial substring filtering by User ID and pagination parameters."
)
def get_orders(
    user_id: Optional[str] = Query(None, description="Search/Filter by User ID (e.g. '101' or 'user-101')"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of orders to return"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
    db: Session = Depends(get_db)
):
    """
    Returns an immutable audit log of synthetic order receipts ordered by newest timestamp first.
    """
    return OrderService.get_orders(db, user_id=user_id, limit=limit, offset=offset)
