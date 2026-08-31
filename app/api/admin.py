import logging
import datetime
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.orm import Session
from app.db.database import get_db
from app.models.folio import Folio, FolioStock
from app.models.subscription import Subscription
from app.models.rebalance_job import RebalanceJob
from app.models.rebalance_task import RebalanceTaskRecord
from app.schemas.admin import RebalanceRequest
from app.workers.rebalance_worker import rebalance_worker

logger = logging.getLogger("api_admin")
router = APIRouter(prefix="/api/admin", tags=["Admin"])

@router.post(
    "/rebalance",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Trigger Asynchronous Folio Rebalance",
    description="Swap a stock inside a Folio (e.g. replace `RELIANCE` with `IDEA`). Validates business invariants, atomically claims the Folio rebalance lock via conditional SQL update, creates a RebalanceJob batch, and enqueues durable background tasks for active subscribers.",
    responses={
        202: {"description": "Rebalance request accepted and fan-out cascade queued asynchronously."},
        400: {"description": "Validation error (e.g. outgoing stock missing or incoming stock duplicate)."},
        404: {"description": "Target Folio not found."},
        409: {"description": "Rebalance conflict: Folio is currently undergoing another rebalancing operation."}
    }
)
def trigger_rebalance(payload: RebalanceRequest, db: Session = Depends(get_db)):
    """
    Triggers an asynchronous stock replacement cascade across all active subscribers of a Folio.
    Validates domain parameters first, then acquires the atomic conditional lock.
    """
    # 1. Fetch target folio
    folio = db.query(Folio).filter(Folio.id == payload.folio_id).first()
    if not folio:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Folio with ID {payload.folio_id} not found"
        )

    # 2. Validation: Find outgoing stock in the folio
    outgoing_stock = next((s for s in folio.stocks if s.ticker.upper() == payload.outgoing_ticker.upper()), None)
    if not outgoing_stock:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Outgoing stock '{payload.outgoing_ticker}' does not exist in Folio '{folio.name}'"
        )

    # 3. Validation: Verify incoming stock is not already present
    incoming_stock_exists = any(s.ticker.upper() == payload.incoming_ticker.upper() for s in folio.stocks)
    if incoming_stock_exists:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Incoming stock '{payload.incoming_ticker}' already exists in Folio '{folio.name}'"
        )

    # 4. Validation: Validate incoming base quantity
    incoming_base_qty = payload.new_base_quantity if payload.new_base_quantity is not None else outgoing_stock.base_quantity
    if incoming_base_qty <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="New base quantity must be positive"
        )

    old_ticker = outgoing_stock.ticker
    old_base_qty = outgoing_stock.base_quantity

    # 5. Atomic Conditional Lock: Atomically claim rebalance state via conditional SQL UPDATE
    lock_query = text(
        "UPDATE folios SET is_rebalancing = 1, rebalance_status = 'REBALANCING' WHERE id = :id AND is_rebalancing = 0"
    )
    result = db.execute(lock_query, {"id": payload.folio_id})
    db.flush()

    if result.rowcount == 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Rebalance already in progress for Folio '{folio.name}'. Please wait until pending tasks finish."
        )

    db.refresh(folio)

    # 6. Atomic database swap, RebalanceJob creation & durable task enqueuing
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

        # Create parent RebalanceJob record
        job = RebalanceJob(
            folio_id=folio.id,
            outgoing_ticker=old_ticker,
            incoming_ticker=payload.incoming_ticker.upper(),
            outgoing_base_quantity=old_base_qty,
            incoming_base_quantity=incoming_base_qty,
            status="PROCESSING" if active_subs else "COMPLETED",
            total_tasks=len(active_subs),
            completed_tasks=0,
            failed_tasks=0,
            completed_at=datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None) if not active_subs else None
        )
        db.add(job)
        db.flush()

        if not active_subs:
            # No subscribers to rebalance; immediately release lock and bump version
            folio.is_rebalancing = False
            folio.version_id += 1
            folio.rebalance_status = "COMPLETED"
        else:
            # Insert durable child task records linked to the job
            for sub in active_subs:
                task_rec = RebalanceTaskRecord(
                    job_id=job.id,
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
        logger.exception("Failed to update Folio composition during rebalance")
        # Reset lock safely
        try:
            with db.begin():
                db.execute(text("UPDATE folios SET is_rebalancing = 0, rebalance_status = 'IDLE' WHERE id = :id"), {"id": payload.folio_id})
        except Exception:
            pass
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update Folio composition. Please try again."
        )

    # 7. Signal durable worker
    rebalance_worker.notify()

    return {
        "message": "Rebalance triggered successfully.",
        "job_id": job.id,
        "outgoing_ticker": old_ticker,
        "incoming_ticker": payload.incoming_ticker.upper(),
        "active_subscribers_queued": len(active_subs)
    }

@router.get(
    "/queue",
    summary="Get Worker Queue Diagnostics",
    description="Retrieve live telemetry and queue counts for background rebalance tasks and batch jobs (`pending`, `processing`, `completed`, `failed`)."
)
def get_queue_status():
    """
    Returns real-time worker execution diagnostics, batch job metrics, and task queue counts.
    """
    return rebalance_worker.get_metrics()
