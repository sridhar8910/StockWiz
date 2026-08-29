import pytest
from app.db.database import SessionLocal
from app.models.folio import Folio
from app.models.subscription import Subscription
from app.models.order import Order

def test_exit_subscription_success(client):
    # 1. Create a subscription first
    subscribe_payload = {
        "user_id": "user-exit-test",
        "folio_id": 1,
        "multiplier": 5.0
    }
    sub_res = client.post("/api/subscriptions", json=subscribe_payload)
    assert sub_res.status_code == 201
    sub_id = sub_res.json()["subscription"]["id"]
    
    # 2. Trigger the exit
    exit_res = client.post(f"/api/subscriptions/{sub_id}/exit")
    assert exit_res.status_code == 200
    
    data = exit_res.json()
    assert "subscription" in data
    assert "orders" in data
    
    sub_data = data["subscription"]
    assert sub_data["id"] == sub_id
    assert sub_data["active"] is False
    
    orders_data = data["orders"]
    assert len(orders_data) == 12
    
    # Verify DB state
    db = SessionLocal()
    try:
        db_sub = db.query(Subscription).filter(Subscription.id == sub_id).first()
        assert db_sub.active is False
        
        # Query the sell orders
        db_orders = db.query(Order).filter(
            Order.subscription_id == sub_id,
            Order.action == "SELL"
        ).all()
        assert len(db_orders) == 12
        
        # Match sell order quantities (should be base_qty * 5.0)
        folio = db.query(Folio).filter(Folio.id == 1).first()
        stocks_map = {s.ticker: s.base_quantity for s in folio.stocks}
        
        for o in db_orders:
            assert o.action == "SELL"
            expected_qty = stocks_map[o.ticker] * 5.0
            assert o.quantity == expected_qty
    finally:
        db.close()

def test_exit_already_inactive_subscription(client):
    # 1. Subscribe
    subscribe_payload = {
        "user_id": "user-exit-double-test",
        "folio_id": 1,
        "multiplier": 1.0
    }
    sub_res = client.post("/api/subscriptions", json=subscribe_payload)
    sub_id = sub_res.json()["subscription"]["id"]
    
    # 2. Exit once (success)
    exit1 = client.post(f"/api/subscriptions/{sub_id}/exit")
    assert exit1.status_code == 200
    
    # 3. Exit again (should fail)
    exit2 = client.post(f"/api/subscriptions/{sub_id}/exit")
    assert exit2.status_code == 400
    assert "already inactive" in exit2.json()["detail"]
