from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.db.database import get_db
from app.schemas.subscription import SubscriptionCreate, SubscriptionResponse, SubscriptionResult
from app.services.subscription_service import SubscriptionService

router = APIRouter(tags=["Subscriptions"])

@router.post("/api/subscriptions", response_model=SubscriptionResult, status_code=status.HTTP_201_CREATED)
def subscribe(payload: SubscriptionCreate, db: Session = Depends(get_db)):
    """
    Subscribe a user to a folio with a multiplier.
    Automatically executes BUY orders for all 12 stocks in the folio.
    """
    try:
        sub, orders = SubscriptionService.subscribe(
            db=db,
            user_id=payload.user_id,
            folio_id=payload.folio_id,
            multiplier=payload.multiplier
        )
        return {
            "subscription": {
                "id": sub.id,
                "user_id": sub.user_id,
                "folio_id": sub.folio_id,
                "multiplier": sub.multiplier,
                "active": sub.active,
                "folio_name": sub.folio.name if sub.folio else None
            },
            "orders": orders
        }
    except ValueError as e:
        msg = str(e)
        if "not found" in msg.lower():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=msg)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)

@router.post("/api/subscriptions/{subscription_id}/exit", response_model=SubscriptionResult)
def exit_subscription(subscription_id: int, db: Session = Depends(get_db)):
    """
    Exit an active folio subscription.
    Deactivates the subscription and executes SELL orders for all current stocks.
    """
    try:
        sub, orders = SubscriptionService.exit_subscription(db, subscription_id)
        return {
            "subscription": {
                "id": sub.id,
                "user_id": sub.user_id,
                "folio_id": sub.folio_id,
                "multiplier": sub.multiplier,
                "active": sub.active,
                "folio_name": sub.folio.name if sub.folio else None
            },
            "orders": orders
        }
    except ValueError as e:
        msg = str(e)
        if "not found" in msg.lower():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=msg)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)

@router.get("/api/users/{user_id}/subscriptions", response_model=List[SubscriptionResponse])
def get_user_subscriptions(user_id: str, db: Session = Depends(get_db)):
    """
    List all active and inactive subscriptions for a given user ID.
    """
    if not user_id or not user_id.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User ID cannot be empty")
        
    subs = SubscriptionService.get_user_subscriptions(db, user_id)
    return [
        {
            "id": s.id,
            "user_id": s.user_id,
            "folio_id": s.folio_id,
            "multiplier": s.multiplier,
            "active": s.active,
            "folio_name": s.folio.name if s.folio else None
        }
        for s in subs
    ]
