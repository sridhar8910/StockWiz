from sqlalchemy import Column, Integer, String, Float, ForeignKey, Boolean, UniqueConstraint, CheckConstraint
from sqlalchemy.orm import relationship
from app.db.database import Base

class Folio(Base):
    __tablename__ = "folios"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True, nullable=False)
    version_id = Column(Integer, default=1, nullable=False)
    is_rebalancing = Column(Boolean, default=False, nullable=False)
    rebalance_status = Column(String, default="IDLE", nullable=False)  # IDLE, REBALANCING, COMPLETED, PARTIAL_FAILURE

    stocks = relationship("FolioStock", back_populates="folio", cascade="all, delete-orphan", lazy="joined")

class FolioStock(Base):
    __tablename__ = "folio_stocks"

    id = Column(Integer, primary_key=True, index=True)
    folio_id = Column(Integer, ForeignKey("folios.id", ondelete="CASCADE"), nullable=False)
    ticker = Column(String, index=True, nullable=False)
    base_quantity = Column(Float, nullable=False)

    folio = relationship("Folio", back_populates="stocks")

    __table_args__ = (
        UniqueConstraint("folio_id", "ticker", name="uq_folio_ticker"),
        CheckConstraint("base_quantity > 0", name="ck_base_quantity_positive"),
        CheckConstraint("length(ticker) > 0", name="ck_ticker_non_empty"),
    )
