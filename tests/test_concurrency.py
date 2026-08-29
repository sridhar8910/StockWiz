import pytest
from app.db.database import SessionLocal
from app.models.folio import Folio

def test_concurrent_rebalance_guard(client):
    # Set folio is_rebalancing to True to simulate active rebalance in progress
    db = SessionLocal()
    try:
        folio = db.query(Folio).filter(Folio.id == 1).first()
        folio.is_rebalancing = True
        db.commit()
    finally:
        db.close()

    # Attempt second concurrent rebalance
    res = client.post("/api/admin/rebalance", json={
        "folio_id": 1,
        "outgoing_ticker": "RELIANCE",
        "incoming_ticker": "IDEA"
    })
    
    assert res.status_code == 409
    assert "already in progress" in res.json()["detail"].lower()

    # Clean up lock
    db = SessionLocal()
    try:
        folio = db.query(Folio).filter(Folio.id == 1).first()
        folio.is_rebalancing = False
        db.commit()
    finally:
        db.close()
