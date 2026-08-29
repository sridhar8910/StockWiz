from typing import List, Optional
from pydantic import BaseModel, Field, field_validator, ConfigDict

def parse_folio_id(val: str | int) -> int:
    if isinstance(val, int):
        return val
    if isinstance(val, str):
        if val.startswith("folio-"):
            try:
                return int(val[len("folio-"):])
            except ValueError:
                raise ValueError("Invalid folio ID format (must end with an integer)")
        try:
            return int(val)
        except ValueError:
            raise ValueError("Invalid folio ID format (must be an integer or folio-<integer>)")
    raise ValueError("folio_id must be a string or integer")

class FolioStockBase(BaseModel):
    ticker: str = Field(..., min_length=1, description="Stock ticker symbol")
    base_quantity: float = Field(..., gt=0, description="Base quantity of the stock in the folio")

class FolioStock(FolioStockBase):
    id: int
    folio_id: int

    model_config = ConfigDict(from_attributes=True)

class FolioBase(BaseModel):
    name: str = Field(..., min_length=1, description="Name of the folio")

class Folio(FolioBase):
    id: int
    stocks: List[FolioStock]

    model_config = ConfigDict(from_attributes=True)
