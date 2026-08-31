import datetime
from sqlalchemy import Column, Integer, String, Float, ForeignKey, DateTime, CheckConstraint
from sqlalchemy.orm import relationship
from app.db.database import Base

class RebalanceTaskRecord(Base):
    __tablename__ = "rebalance_tasks"

    id = Column(Integer, primary_key=True, index=True)
    job_id = Column(Integer, ForeignKey("rebalance_jobs.id", ondelete="CASCADE"), nullable=True, index=True)
    folio_id = Column(Integer, ForeignKey("folios.id", ondelete="CASCADE"), nullable=False)
    subscription_id = Column(Integer, ForeignKey("subscriptions.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(String, index=True, nullable=False)
    outgoing_ticker = Column(String, nullable=False)
    incoming_ticker = Column(String, nullable=False)
    multiplier = Column(Float, nullable=False)
    outgoing_base_qty = Column(Float, nullable=False)
    incoming_base_qty = Column(Float, nullable=False)
    status = Column(String, default="PENDING", index=True, nullable=False)  # PENDING, PROCESSING, COMPLETED, FAILED
    worker_id = Column(String, nullable=True, index=True)
    claimed_at = Column(DateTime, nullable=True)
    lease_until = Column(DateTime, nullable=True)
    error_message = Column(String, nullable=True)
    retries = Column(Integer, default=0, nullable=False)
    next_retry_at = Column(DateTime, nullable=True)
    created_at = Column(
        DateTime,
        default=lambda: datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None),
        nullable=False
    )
    completed_at = Column(DateTime, nullable=True)

    job = relationship("RebalanceJob", back_populates="tasks")

    __table_args__ = (
        CheckConstraint("multiplier > 0", name="ck_task_multiplier_positive"),
        CheckConstraint("outgoing_base_qty > 0", name="ck_task_out_base_positive"),
        CheckConstraint("incoming_base_qty > 0", name="ck_task_in_base_positive"),
        CheckConstraint("status IN ('PENDING', 'PROCESSING', 'COMPLETED', 'FAILED')", name="ck_task_status_valid"),
    )
