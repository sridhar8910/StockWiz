from typing import List
from fastapi import APIRouter, Depends, HTTPException, Path, status
from sqlalchemy.orm import Session
from app.db.database import get_db
from app.schemas.subscription import SubscriptionCreate, SubscriptionResponse, SubscriptionResult
from app.services.subscription_service import SubscriptionService

router = APIRouter(tags=["Subscriptions"])

@router.post(
    "/api/subscriptions",
    response_model=SubscriptionResult,
    status_code=status.HTTP_201_CREATED,
    summary="Subscribe to a Folio",
    description="Subscribe a user to a selected Folio with a configurable multiplier (`1x`, `2x`, `3x`, `5x`). Atomically executes **12 synthetic BUY orders** sized as `Base Quantity × User Multiplier`.",
    responses={
        201: {"description": "Subscription created and 12 BUY orders executed successfully."},
        400: {"description": "Validation error (e.g. invalid multiplier, duplicate active subscription)."},
        404: {"description": "Folio not found."}
    }
)
def subscribe(payload: SubscriptionCreate, db: Session = Depends(get_db)):
    """
    Subscribe a user to a folio with a multiplier.
    Automatically executes 12 BUY orders sized at `base_quantity * multiplier`.
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

@router.post(
    "/api/subscriptions/{subscription_id}/exit",
    response_model=SubscriptionResult,
    summary="Exit Folio Subscription",
    description="Liquidate an active Folio subscription. Atomically marks the subscription inactive and executes **12 synthetic SELL orders** matching the user's multiplier positions.",
    responses={
        200: {"description": "Subscription exited and 12 SELL orders executed successfully."},
        400: {"description": "Subscription is already inactive."},
        404: {"description": "Subscription or Folio not found."}
    }
)
def exit_subscription(
    subscription_id: int = Path(..., description="Unique Subscription ID to exit"),
    db: Session = Depends(get_db)
):
    """
    Exit an active folio subscription and liquidate all current positions.
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

@router.get(
    "/api/users/{user_id}/subscriptions",
    response_model=List[SubscriptionResponse],
    summary="List User Subscriptions",
    description="Retrieve all active and exited Folio subscriptions associated with a given User ID."
)
def get_user_subscriptions(
    user_id: str = Path(..., description="User ID (e.g. 'user-101')"),
    db: Session = Depends(get_db)
):
    """
    List all subscriptions for a specific user.
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
