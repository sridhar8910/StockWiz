from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.db.database import get_db
from app.models.folio import Folio, FolioStock
from app.models.subscription import Subscription
from app.models.rebalance_task import RebalanceTaskRecord
from app.schemas.admin import RebalanceRequest
from app.workers.rebalance_worker import rebalance_worker

router = APIRouter(prefix="/api/admin", tags=["Admin"])

@router.post("/rebalance", status_code=status.HTTP_202_ACCEPTED)
def trigger_rebalance(payload: RebalanceRequest, db: Session = Depends(get_db)):
    """
    Trigger stock rebalancing inside a Folio.
    Updates the folio composition, saves durable task records, and schedules an asynchronous cascade.
    """
    # 1. Fetch and validate folio
    folio = db.query(Folio).filter(Folio.id == payload.folio_id).first()
    if not folio:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Folio with ID {payload.folio_id} not found"
        )

    # 2. Concurrency check: guard against simultaneous rebalances on same folio
    if folio.is_rebalancing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Rebalancing is already in progress for Folio '{folio.name}'. Please wait until pending tasks finish."
        )

    # 3. Find outgoing stock in the folio
    outgoing_stock = next((s for s in folio.stocks if s.ticker.upper() == payload.outgoing_ticker.upper()), None)
    if not outgoing_stock:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Outgoing stock '{payload.outgoing_ticker}' does not exist in Folio '{folio.name}'"
        )

    # 4. Verify incoming stock is not already present
    incoming_stock_exists = any(s.ticker.upper() == payload.incoming_ticker.upper() for s in folio.stocks)
    if incoming_stock_exists:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Incoming stock '{payload.incoming_ticker}' already exists in Folio '{folio.name}'"
        )

    # 5. Validate quantity
    incoming_base_qty = payload.new_base_quantity if payload.new_base_quantity is not None else outgoing_stock.base_quantity
    if incoming_base_qty <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="New base quantity must be positive"
        )

    # Keep track of old details for rebalancing tasks
    old_ticker = outgoing_stock.ticker
    old_base_qty = outgoing_stock.base_quantity

    # 6. Atomic database swap & durable task creation
    try:
        db.delete(outgoing_stock)
        db.flush()

        new_stock = FolioStock(
            folio_id=folio.id,
            ticker=payload.incoming_ticker.upper(),
            base_quantity=incoming_base_qty
        )
        db.add(new_stock)
        db.flush()

        # Fetch all active subscriptions
        active_subs = db.query(Subscription).filter(
            Subscription.folio_id == folio.id,
            Subscription.active == True
        ).all()

        # Set folio rebalancing lock if there are subscribers
        if active_subs:
            folio.is_rebalancing = True

        # Insert durable task records into the database
        for sub in active_subs:
            task_rec = RebalanceTaskRecord(
                folio_id=folio.id,
                subscription_id=sub.id,
                user_id=sub.user_id,
                outgoing_ticker=old_ticker,
                incoming_ticker=payload.incoming_ticker.upper(),
                multiplier=sub.multiplier,
                outgoing_base_qty=old_base_qty,
                incoming_base_qty=incoming_base_qty,
                status="PENDING"
            )
            db.add(task_rec)

        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update Folio composition: {str(e)}"
        )

    # 7. Notify background worker
    rebalance_worker.notify()

    return {
        "message": "Rebalance triggered successfully.",
        "outgoing_ticker": old_ticker,
        "incoming_ticker": payload.incoming_ticker.upper(),
        "active_subscribers_queued": len(active_subs)
    }

@router.get("/queue")
def get_queue_status():
    """
    Get the durable status and metrics of the background rebalancing task worker.
    """
    return rebalance_worker.get_metrics()
