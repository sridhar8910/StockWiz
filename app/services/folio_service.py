from typing import List, Optional
from sqlalchemy.orm import Session
from app.models.folio import Folio, FolioStock

class FolioService:
    @staticmethod
    def get_all_folios(db: Session) -> List[Folio]:
        return db.query(Folio).all()

    @staticmethod
    def get_folio_by_id(db: Session, folio_id: int) -> Optional[Folio]:
        return db.query(Folio).filter(Folio.id == folio_id).first()

    @staticmethod
    def get_stock_in_folio(db: Session, folio_id: int, ticker: str) -> Optional[FolioStock]:
        return db.query(FolioStock).filter(
            FolioStock.folio_id == folio_id,
            FolioStock.ticker == ticker
        ).first()
