import datetime
from sqlalchemy import Column, Integer, String, Float, ForeignKey, DateTime
from app.db.database import Base

class RebalanceTaskRecord(Base):
    __tablename__ = "rebalance_tasks"

    id = Column(Integer, primary_key=True, index=True)
    folio_id = Column(Integer, ForeignKey("folios.id", ondelete="CASCADE"), nullable=False)
    subscription_id = Column(Integer, ForeignKey("subscriptions.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(String, index=True, nullable=False)
    outgoing_ticker = Column(String, nullable=False)
    incoming_ticker = Column(String, nullable=False)
    multiplier = Column(Float, nullable=False)
    outgoing_base_qty = Column(Float, nullable=False)
    incoming_base_qty = Column(Float, nullable=False)
    status = Column(String, default="PENDING", index=True, nullable=False)  # PENDING, PROCESSING, COMPLETED, FAILED
    error_message = Column(String, nullable=True)
    retries = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None), nullable=False)
    completed_at = Column(DateTime, nullable=True)
