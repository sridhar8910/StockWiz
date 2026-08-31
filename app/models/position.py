import datetime
from sqlalchemy import Column, Integer, String, Float, ForeignKey, DateTime, Index
from sqlalchemy.orm import relationship
from app.db.database import Base

class Position(Base):
    __tablename__ = "positions"

    id = Column(Integer, primary_key=True, index=True)
    subscription_id = Column(Integer, ForeignKey("subscriptions.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(String, index=True, nullable=False)
    ticker = Column(String, index=True, nullable=False)
    quantity = Column(Float, nullable=False)
    status = Column(String, default="ACTIVE", nullable=False)  # ACTIVE, LIQUIDATED
    updated_at = Column(
        DateTime,
        default=lambda: datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None),
        onupdate=lambda: datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None),
        nullable=False
    )

    subscription = relationship("Subscription", back_populates="positions")

    __table_args__ = (
        Index("ix_sub_ticker_active", "subscription_id", "ticker", "status"),
    )
