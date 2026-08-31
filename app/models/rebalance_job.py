import datetime
from sqlalchemy import Column, Integer, String, Float, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from app.db.database import Base

class RebalanceJob(Base):
    __tablename__ = "rebalance_jobs"

    id = Column(Integer, primary_key=True, index=True)
    folio_id = Column(Integer, ForeignKey("folios.id", ondelete="CASCADE"), nullable=False, index=True)
    outgoing_ticker = Column(String, nullable=False)
    incoming_ticker = Column(String, nullable=False)
    outgoing_base_quantity = Column(Float, nullable=False)
    incoming_base_quantity = Column(Float, nullable=False)
    status = Column(String, default="PENDING", index=True, nullable=False)  # PENDING, PROCESSING, COMPLETED, PARTIAL_FAILURE, FAILED
    total_tasks = Column(Integer, default=0, nullable=False)
    completed_tasks = Column(Integer, default=0, nullable=False)
    failed_tasks = Column(Integer, default=0, nullable=False)
    created_at = Column(
        DateTime,
        default=lambda: datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None),
        nullable=False
    )
    completed_at = Column(DateTime, nullable=True)

    folio = relationship("Folio", lazy="joined")
    tasks = relationship("RebalanceTaskRecord", back_populates="job", cascade="all, delete-orphan")
