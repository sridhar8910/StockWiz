import asyncio
import datetime
import logging
from typing import Dict, Any
from sqlalchemy.orm import Session
from app.db.database import SessionLocal
from app.services.broker_service import BrokerService
from app.models.order import Order
from app.models.subscription import Subscription
from app.models.folio import Folio
from app.models.rebalance_task import RebalanceTaskRecord

logger = logging.getLogger("rebalance_worker")
logging.basicConfig(level=logging.INFO)

class RebalanceWorker:
    def __init__(self):
        self._notify_event: asyncio.Event | None = None
        self.worker_task: asyncio.Task | None = None
        self.is_running = False

    def notify(self) -> None:
        """Signal worker that new tasks were added to DB."""
        if self._notify_event is not None:
            self._notify_event.set()

    def get_metrics(self) -> Dict[str, Any]:
        """Fetch durable real-time metrics from the database."""
        db: Session = SessionLocal()
        try:
            pending = db.query(RebalanceTaskRecord).filter(RebalanceTaskRecord.status == "PENDING").count()
            processing = db.query(RebalanceTaskRecord).filter(RebalanceTaskRecord.status == "PROCESSING").count()
            completed = db.query(RebalanceTaskRecord).filter(RebalanceTaskRecord.status == "COMPLETED").count()
            failed = db.query(RebalanceTaskRecord).filter(RebalanceTaskRecord.status == "FAILED").count()
            total = db.query(RebalanceTaskRecord).count()
            return {
                "pending_count": pending + processing,
                "processing_count": processing,
                "completed_count": completed,
                "failed_count": failed,
                "total_queued": total,
                "is_running": self.worker_task is not None and not self.worker_task.done()
            }
        finally:
            db.close()

    def get_pending_count(self) -> int:
        metrics = self.get_metrics()
        return metrics["pending_count"]

    @property
    def processed_count(self) -> int:
        metrics = self.get_metrics()
        return metrics["completed_count"]

    @property
    def total_queued(self) -> int:
        metrics = self.get_metrics()
        return metrics["total_queued"]

    def start(self) -> None:
        if self.worker_task is None or self.worker_task.done():
            self._notify_event = asyncio.Event()
            self.is_running = True
            self.worker_task = asyncio.create_task(self._worker_loop())
            logger.info("Durable Rebalance Worker started.")

    async def stop(self) -> None:
        self.is_running = False
        if self.worker_task:
            self.worker_task.cancel()
            try:
                await self.worker_task
            except asyncio.CancelledError:
                pass
            self.worker_task = None
            self._notify_event = None
            logger.info("Durable Rebalance Worker stopped.")

    async def _worker_loop(self) -> None:
        # Recover any stuck tasks on startup
        self._recover_stuck_tasks()
        
        while self.is_running:
            processed_any = await self._process_next_batch()
            if not processed_any:
                # Wait for next notification or periodic wake-up
                if self._notify_event:
                    try:
                        await asyncio.wait_for(self._notify_event.wait(), timeout=0.5)
                        self._notify_event.clear()
                    except asyncio.TimeoutError:
                        pass
                else:
                    await asyncio.sleep(0.5)

    def _recover_stuck_tasks(self) -> None:
        """Reset PROCESSING tasks back to PENDING on startup to recover from server crashes."""
        db: Session = SessionLocal()
        try:
            stuck_tasks = db.query(RebalanceTaskRecord).filter(RebalanceTaskRecord.status == "PROCESSING").all()
            for t in stuck_tasks:
                t.status = "PENDING"
            if stuck_tasks:
                db.commit()
                logger.info(f"Recovered {len(stuck_tasks)} stuck rebalance tasks.")
        except Exception as e:
            db.rollback()
            logger.error(f"Error recovering stuck tasks: {e}")
        finally:
            db.close()

    async def _process_next_batch(self) -> bool:
        db: Session = SessionLocal()
        task_id = None
        try:
            task = db.query(RebalanceTaskRecord).filter(RebalanceTaskRecord.status == "PENDING").order_by(RebalanceTaskRecord.id).first()
            if not task:
                return False

            task.status = "PROCESSING"
            db.commit()
            task_id = task.id
        except Exception as e:
            db.rollback()
            logger.error(f"Error fetching pending task: {e}")
            return False
        finally:
            db.close()

        if task_id:
            await self._process_single_task(task_id)
            return True
        return False

    async def _process_single_task(self, task_id: int) -> None:
        db: Session = SessionLocal()
        try:
            task = db.query(RebalanceTaskRecord).filter(RebalanceTaskRecord.id == task_id).first()
            if not task:
                return

            sub = db.query(Subscription).filter(Subscription.id == task.subscription_id).first()
            if not sub or not sub.active:
                task.status = "COMPLETED"
                task.completed_at = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
                task.error_message = "Subscription inactive or cancelled; skipped."
                db.commit()
                self._check_folio_rebalance_complete(db, task.folio_id)
                return

            # Execute Step 1: SELL outgoing stock
            sell_qty = task.outgoing_base_qty * task.multiplier
            sell_idemp = f"rebal-{task.id}-{task.outgoing_ticker}-SELL"
            sell_receipt = BrokerService.execute_trade(
                user_id=task.user_id,
                ticker=task.outgoing_ticker,
                action="SELL",
                quantity=sell_qty,
                idempotency_key=sell_idemp
            )
            sell_order = Order(
                order_id=sell_receipt["order_id"],
                user_id=task.user_id,
                subscription_id=task.subscription_id,
                ticker=task.outgoing_ticker,
                action="SELL",
                quantity=sell_qty,
                status=sell_receipt["status"],
                idempotency_key=sell_idemp,
                timestamp=sell_receipt["timestamp"]
            )
            db.add(sell_order)

            # Execute Step 2: BUY incoming stock
            buy_qty = task.incoming_base_qty * task.multiplier
            buy_idemp = f"rebal-{task.id}-{task.incoming_ticker}-BUY"
            buy_receipt = BrokerService.execute_trade(
                user_id=task.user_id,
                ticker=task.incoming_ticker,
                action="BUY",
                quantity=buy_qty,
                idempotency_key=buy_idemp
            )
            buy_order = Order(
                order_id=buy_receipt["order_id"],
                user_id=task.user_id,
                subscription_id=task.subscription_id,
                ticker=task.incoming_ticker,
                action="BUY",
                quantity=buy_qty,
                status=buy_receipt["status"],
                idempotency_key=buy_idemp,
                timestamp=buy_receipt["timestamp"]
            )
            db.add(buy_order)

            task.status = "COMPLETED"
            task.completed_at = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
            db.commit()
            logger.info(f"Durable Rebalance Completed for Task {task.id} (User: {task.user_id})")

            self._check_folio_rebalance_complete(db, task.folio_id)
        except Exception as e:
            db.rollback()
            logger.error(f"Error processing task {task_id}: {e}", exc_info=True)
            try:
                db_fail = SessionLocal()
                t = db_fail.query(RebalanceTaskRecord).filter(RebalanceTaskRecord.id == task_id).first()
                if t:
                    t.retries += 1
                    t.status = "FAILED" if t.retries >= 3 else "PENDING"
                    t.error_message = str(e)
                    db_fail.commit()
                    self._check_folio_rebalance_complete(db_fail, t.folio_id)
                db_fail.close()
            except Exception:
                pass
        finally:
            db.close()

    def _check_folio_rebalance_complete(self, db: Session, folio_id: int) -> None:
        """If all rebalance tasks for the folio are finished, release folio lock."""
        try:
            remaining = db.query(RebalanceTaskRecord).filter(
                RebalanceTaskRecord.folio_id == folio_id,
                RebalanceTaskRecord.status.in_(["PENDING", "PROCESSING"])
            ).count()
            if remaining == 0:
                folio = db.query(Folio).filter(Folio.id == folio_id).first()
                if folio and folio.is_rebalancing:
                    folio.is_rebalancing = False
                    folio.version_id += 1
                    db.commit()
                    logger.info(f"Folio {folio_id} rebalancing finished and lock released.")
        except Exception as e:
            logger.error(f"Error checking folio completion: {e}")

# Shared singleton instance
rebalance_worker = RebalanceWorker()
