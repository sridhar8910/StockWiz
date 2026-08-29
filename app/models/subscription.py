from sqlalchemy import Column, Integer, String, Float, ForeignKey, Boolean
from sqlalchemy.orm import relationship
from app.db.database import Base

class Subscription(Base):
    __tablename__ = "subscriptions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String, index=True, nullable=False)
    folio_id = Column(Integer, ForeignKey("folios.id"), nullable=False)
    multiplier = Column(Float, nullable=False)
    active = Column(Boolean, default=True, nullable=False)

    # Useful relationship to get folio name easily
    folio = relationship("Folio", lazy="joined")
