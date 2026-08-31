import datetime
from sqlalchemy import Column, Integer, String, Float, ForeignKey, DateTime, CheckConstraint
from app.db.database import Base

class Order(Base):
    __tablename__ = "orders"

    order_id = Column(String, primary_key=True, index=True)
    user_id = Column(String, index=True, nullable=False)
    subscription_id = Column(Integer, ForeignKey("subscriptions.id", ondelete="SET NULL"), nullable=True)
    ticker = Column(String, index=True, nullable=False)
    action = Column(String, nullable=False)  # BUY or SELL
    quantity = Column(Float, nullable=False)
    status = Column(String, default="EXECUTED", nullable=False)   # PENDING, EXECUTED, FAILED, CANCELLED
    idempotency_key = Column(String, unique=True, index=True, nullable=True)
    timestamp = Column(DateTime, default=lambda: datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None), nullable=False)

    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_order_quantity_positive"),
        CheckConstraint("action IN ('BUY', 'SELL')", name="ck_order_action_valid"),
        CheckConstraint("status IN ('PENDING', 'EXECUTED', 'FAILED', 'CANCELLED')", name="ck_order_status_valid"),
    )
