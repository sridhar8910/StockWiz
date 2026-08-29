from typing import List
from fastapi import APIRouter, Depends, HTTPException, Path, status
from sqlalchemy.orm import Session
from app.db.database import get_db
from app.schemas.folio import Folio as FolioSchema
from app.services.folio_service import FolioService

router = APIRouter(prefix="/api/folios", tags=["Folios"])

@router.get(
    "",
    response_model=List[FolioSchema],
    summary="List all Folios",
    description="Retrieve all 7 pre-seeded thematic Folios along with their 12-stock composition, base quantities, and revision version IDs."
)
def get_folios(db: Session = Depends(get_db)):
    """
    Returns the list of all available Folios.
    Each Folio contains exactly 12 stock constituents.
    """
    return FolioService.get_all_folios(db)

@router.get(
    "/{folio_id}",
    response_model=FolioSchema,
    summary="Get Folio by ID",
    description="Retrieve detailed stock composition of a specific Folio by integer ID (e.g. `1`) or string identifier (e.g. `'folio-1'`).",
    responses={
        400: {"description": "Invalid Folio ID format."},
        404: {"description": "Folio not found."}
    }
)
def get_folio(
    folio_id: str = Path(..., description="Folio ID as integer or 'folio-<id>' string format"),
    db: Session = Depends(get_db)
):
    """
    Fetch a single Folio with its full 12-stock breakdown.
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
