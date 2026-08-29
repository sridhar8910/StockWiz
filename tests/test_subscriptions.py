import pytest
from app.db.database import SessionLocal
from app.models.folio import Folio
from app.models.subscription import Subscription
from app.models.order import Order

def test_subscribe_success(client):
    # Step 1: Subscribe user-101 to Folio 1 (Alpha Growth) with 3x multiplier
    payload = {
        "user_id": "user-101",
        "folio_id": 1,
        "multiplier": 3.0
    }
    
    response = client.post("/api/subscriptions", json=payload)
    assert response.status_code == 201
    
    data = response.json()
    assert "subscription" in data
    assert "orders" in data
    
    sub_data = data["subscription"]
    assert sub_data["user_id"] == "user-101"
    assert sub_data["folio_id"] == 1
    assert sub_data["multiplier"] == 3.0
    assert sub_data["active"] is True
    assert sub_data["folio_name"] == "Alpha Growth"
    
    orders_data = data["orders"]
    assert len(orders_data) == 12
    
    # Verify DB state directly
    db = SessionLocal()
    try:
        # Check subscription record
        db_sub = db.query(Subscription).filter(Subscription.user_id == "user-101", Subscription.active == True).first()
        assert db_sub is not None
        assert db_sub.multiplier == 3.0
        
        # Check order records
        db_orders = db.query(Order).filter(Order.subscription_id == db_sub.id).all()
        assert len(db_orders) == 12
        
        # Fetch Folio 1 stocks to match base quantities
        folio = db.query(Folio).filter(Folio.id == 1).first()
        stocks_map = {s.ticker: s.base_quantity for s in folio.stocks}
        
        # Match order quantities
        for o in db_orders:
            assert o.action == "BUY"
            assert o.status == "EXECUTED"
            expected_qty = stocks_map[o.ticker] * 3.0
            assert o.quantity == expected_qty
    finally:
        db.close()

def test_subscribe_with_string_folio_id(client):
    # Test support for string folio ID like "folio-1"
    payload = {
        "user_id": "user-102",
        "folio_id": "folio-1",
        "multiplier": 2.0
    }
    
    response = client.post("/api/subscriptions", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["subscription"]["folio_id"] == 1
    assert data["subscription"]["multiplier"] == 2.0
    assert len(data["orders"]) == 12
