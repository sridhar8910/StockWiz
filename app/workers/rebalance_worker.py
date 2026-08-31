import asyncio
import datetime
import logging
from typing import Dict, Any
from sqlalchemy import text
from sqlalchemy.orm import Session
from app.db.database import SessionLocal
from app.services.broker_service import BrokerService
from app.models.order import Order
from app.models.subscription import Subscription
from app.models.folio import Folio
from app.models.position import Position
from app.models.rebalance_job import RebalanceJob
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
            
            active_jobs = db.query(RebalanceJob).filter(RebalanceJob.status.in_(["PENDING", "PROCESSING"])).count()
            total_jobs = db.query(RebalanceJob).count()

            return {
                "pending_count": pending + processing,
                "processing_count": processing,
                "completed_count": completed,
                "failed_count": failed,
                "total_queued": total,
                "active_jobs": active_jobs,
                "total_jobs": total_jobs,
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
        task = self.worker_task
        self.worker_task = None
        self._notify_event = None
        if task:
            try:
                task.cancel()
                try:
                    current_loop = asyncio.get_running_loop()
                    if task.get_loop() == current_loop:
                        await task
                except RuntimeError:
                    pass
            except (asyncio.CancelledError, Exception):
                pass
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
        """Atomically claims a pending task to prevent multi-worker race conditions."""
        db: Session = SessionLocal()
        task_id = None
        now_utc = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
        try:
            # Query candidate task
            candidate = db.query(RebalanceTaskRecord).filter(
                RebalanceTaskRecord.status == "PENDING",
                (RebalanceTaskRecord.next_retry_at == None) | (RebalanceTaskRecord.next_retry_at <= now_utc)
            ).order_by(RebalanceTaskRecord.id).first()

            if not candidate:
                return False

            # Atomic conditional claim: update status to PROCESSING only if still PENDING
            claim_query = text(
                "UPDATE rebalance_tasks SET status = 'PROCESSING' WHERE id = :task_id AND status = 'PENDING'"
            )
            result = db.execute(claim_query, {"task_id": candidate.id})
            db.commit()

            if result.rowcount > 0:
                task_id = candidate.id
            else:
                # Another worker claimed it first
                return True
        except Exception as e:
            db.rollback()
            logger.error(f"Error atomically claiming pending task: {e}")
            return False
        finally:
            db.close()

        if task_id:
            await self._process_single_task(task_id)
            return True
        return False

    async def _process_single_task(self, task_id: int) -> None:
        db: Session = SessionLocal()
        now_utc = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
        job_id = None
        folio_id = None
        try:
            task = db.query(RebalanceTaskRecord).filter(RebalanceTaskRecord.id == task_id).first()
            if not task:
                return

            job_id = task.job_id
            folio_id = task.folio_id

            # Step 0: Subscription lifecycle coordination (ACTIVE -> REBALANCING)
            claim_sub_sql = text(
                "UPDATE subscriptions SET status = 'REBALANCING' WHERE id = :sub_id AND status = 'ACTIVE' AND active = 1"
            )
            sub_claim_res = db.execute(claim_sub_sql, {"sub_id": task.subscription_id})
            db.flush()

            if sub_claim_res.rowcount == 0:
                # Subscription has exited, is exiting, or is inactive
                task.status = "COMPLETED"
                task.completed_at = now_utc
                task.error_message = "Subscription inactive or exited; skipped."
                db.commit()
                self._check_rebalance_complete(db, job_id, folio_id)
                return

            # Step 1: SELL outgoing stock with idempotency guard
            sell_idemp = f"rebal-{task.id}-{task.outgoing_ticker}-SELL"
            existing_sell = db.query(Order).filter(Order.idempotency_key == sell_idemp).first()
            if not existing_sell:
                sell_qty = task.outgoing_base_qty * task.multiplier
                sell_receipt = BrokerService.execute_trade(
                    user_id=task.user_id,
                    ticker=task.outgoing_ticker,
                    action="SELL",
                    quantity=sell_qty,
                    idempotency_key=sell_idemp,
                    db=db
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
                db.flush()

            # Check if user requested exit during SELL
            sub_recheck = db.query(Subscription).filter(Subscription.id == task.subscription_id).first()
            if not sub_recheck or not sub_recheck.active or sub_recheck.status in ("EXITING", "EXITED"):
                # Mark outgoing position liquidated and skip BUY
                outgoing_pos = db.query(Position).filter(
                    Position.subscription_id == task.subscription_id,
                    Position.ticker == task.outgoing_ticker,
                    Position.status == "ACTIVE"
                ).first()
                if outgoing_pos:
                    outgoing_pos.status = "LIQUIDATED"
                    outgoing_pos.updated_at = now_utc

                task.status = "COMPLETED"
                task.completed_at = now_utc
                db.commit()
                self._check_rebalance_complete(db, job_id, folio_id)
                return

            # Step 2: BUY incoming stock with idempotency guard
            buy_idemp = f"rebal-{task.id}-{task.incoming_ticker}-BUY"
            existing_buy = db.query(Order).filter(Order.idempotency_key == buy_idemp).first()
            if not existing_buy:
                buy_qty = task.incoming_base_qty * task.multiplier
                buy_receipt = BrokerService.execute_trade(
                    user_id=task.user_id,
                    ticker=task.incoming_ticker,
                    action="BUY",
                    quantity=buy_qty,
                    idempotency_key=buy_idemp,
                    db=db
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
                db.flush()

            # Step 3: Update user's explicit Position state ledger
            outgoing_pos = db.query(Position).filter(
                Position.subscription_id == task.subscription_id,
                Position.ticker == task.outgoing_ticker,
                Position.status == "ACTIVE"
            ).first()

            if outgoing_pos:
                outgoing_pos.status = "LIQUIDATED"
                outgoing_pos.updated_at = now_utc

            incoming_pos = db.query(Position).filter(
                Position.subscription_id == task.subscription_id,
                Position.ticker == task.incoming_ticker,
                Position.status == "ACTIVE"
            ).first()

            if not incoming_pos:
                new_pos = Position(
                    subscription_id=task.subscription_id,
                    user_id=task.user_id,
                    ticker=task.incoming_ticker,
                    quantity=task.incoming_base_qty * task.multiplier,
                    status="ACTIVE",
                    updated_at=now_utc
                )
                db.add(new_pos)

            # Step 4: Transition subscription lifecycle back (REBALANCING -> ACTIVE)
            release_sub_sql = text(
                "UPDATE subscriptions SET status = 'ACTIVE' WHERE id = :sub_id AND status = 'REBALANCING' AND active = 1"
            )
            db.execute(release_sub_sql, {"sub_id": task.subscription_id})

            task.status = "COMPLETED"
            task.completed_at = now_utc
            db.commit()

            logger.info(f"Durable Rebalance Completed for Task {task.id} (User: {task.user_id}, Job: {job_id})")

            self._check_rebalance_complete(db, job_id, folio_id)
        except Exception as e:
            db.rollback()
            logger.error(f"Error processing task {task_id}: {e}", exc_info=True)
            try:
                db_fail = SessionLocal()
                t = db_fail.query(RebalanceTaskRecord).filter(RebalanceTaskRecord.id == task_id).first()
                if t:
                    t.retries += 1
                    if t.retries >= 3:
                        t.status = "FAILED"
                    else:
                        t.status = "PENDING"
                        delay = min(30, 2 ** t.retries)
                        t.next_retry_at = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None) + datetime.timedelta(seconds=delay)
                    t.error_message = str(e)
                    
                    # Reset subscription status if stuck in REBALANCING
                    db_fail.execute(
                        text("UPDATE subscriptions SET status = 'ACTIVE' WHERE id = :sub_id AND status = 'REBALANCING' AND active = 1"),
                        {"sub_id": t.subscription_id}
                    )
                    db_fail.commit()
                    self._check_rebalance_complete(db_fail, t.job_id, t.folio_id)
                db_fail.close()
            except Exception:
                pass
        finally:
            db.close()

    def _check_rebalance_complete(self, db: Session, job_id: int | None, folio_id: int | None) -> None:
        """Checks if a RebalanceJob is finished and releases the folio lock using RebalanceJob as sole source of truth."""
        now_utc = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
        try:
            if job_id:
                job = db.query(RebalanceJob).filter(RebalanceJob.id == job_id).first()
                if job and job.status in ["PENDING", "PROCESSING"]:
                    pending_tasks = db.query(RebalanceTaskRecord).filter(
                        RebalanceTaskRecord.job_id == job_id,
                        RebalanceTaskRecord.status.in_(["PENDING", "PROCESSING"])
                    ).count()
                    
                    completed_tasks = db.query(RebalanceTaskRecord).filter(
                        RebalanceTaskRecord.job_id == job_id,
                        RebalanceTaskRecord.status == "COMPLETED"
                    ).count()

                    failed_tasks = db.query(RebalanceTaskRecord).filter(
                        RebalanceTaskRecord.job_id == job_id,
                        RebalanceTaskRecord.status == "FAILED"
                    ).count()

                    # Derive exact counter values from source of truth
                    job.completed_tasks = completed_tasks
                    job.failed_tasks = failed_tasks
                    
                    if pending_tasks == 0:
                        if failed_tasks > 0:
                            job.status = "PARTIAL_FAILURE"
                            final_folio_status = "REBALANCE_REQUIRES_RECONCILIATION"
                        else:
                            job.status = "COMPLETED"
                            final_folio_status = "COMPLETED"
                        job.completed_at = now_utc
                        
                        # Release the folio lock strictly based on the completed job
                        folio = db.query(Folio).filter(Folio.id == job.folio_id).first()
                        if folio and folio.is_rebalancing:
                            folio.is_rebalancing = False
                            folio.version_id += 1
                            folio.rebalance_status = final_folio_status
                            logger.info(f"Folio {job.folio_id} rebalance job {job_id} finished with status {job.status} (Folio status: {final_folio_status}).")
                        db.commit()
        except Exception as e:
            logger.error(f"Error checking rebalance completion: {e}")

# Shared singleton instance
rebalance_worker = RebalanceWorker()
