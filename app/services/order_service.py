from typing import List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import desc
from app.models.order import Order

class OrderService:
    @staticmethod
    def get_orders(
        db: Session,
        user_id: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[Order]:
        query = db.query(Order)
        if user_id:
            query = query.filter(Order.user_id == user_id)
        # Order by newest first
        return query.order_by(desc(Order.timestamp)).offset(offset).limit(limit).all()
