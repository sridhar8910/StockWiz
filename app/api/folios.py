from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.db.database import get_db
from app.schemas.folio import Folio as FolioSchema
from app.services.folio_service import FolioService

router = APIRouter(prefix="/api/folios", tags=["Folios"])

@router.get("", response_model=List[FolioSchema])
def get_folios(db: Session = Depends(get_db)):
    """
    List all available folios with their stocks.
    """
    return FolioService.get_all_folios(db)

@router.get("/{folio_id}", response_model=FolioSchema)
def get_folio(folio_id: str, db: Session = Depends(get_db)):
    """
    Get detailed stock composition of a specific folio.
    Supports either integer ID or 'folio-<id>' string format.
    """
    from app.schemas.folio import parse_folio_id
    try:
        parsed_id = parse_folio_id(folio_id)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )

    folio = FolioService.get_folio_by_id(db, parsed_id)
    if not folio:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Folio with ID {folio_id} not found"
        )
    return folio
