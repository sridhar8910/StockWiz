from sqlalchemy import Column, Integer, String, Float, ForeignKey, Boolean, Index, text
from sqlalchemy.orm import relationship
from app.db.database import Base

class Subscription(Base):
    __tablename__ = "subscriptions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String, index=True, nullable=False)
    folio_id = Column(Integer, ForeignKey("folios.id"), nullable=False)
    multiplier = Column(Float, nullable=False)
    active = Column(Boolean, default=True, nullable=False)

    # Relationship to get folio
    folio = relationship("Folio", lazy="joined")
    # Explicit Position ledger
    positions = relationship("Position", back_populates="subscription", cascade="all, delete-orphan")

    __table_args__ = (
        Index(
            "uq_active_user_folio",
            "user_id",
            "folio_id",
            unique=True,
            sqlite_where=text("active = 1"),
            postgresql_where=text("active = true")
        ),
    )
