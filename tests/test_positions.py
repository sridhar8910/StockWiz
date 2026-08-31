import time
import pytest
from app.db.database import SessionLocal
from app.models.position import Position
from app.models.subscription import Subscription
from app.models.folio import Folio

def test_positions_created_on_subscription(client):
    res = client.post("/api/subscriptions", json={
        "user_id": "user-pos-test",
        "folio_id": 1,
        "multiplier": 3.0
    })
    assert res.status_code == 201
    sub_id = res.json()["subscription"]["id"]

    db = SessionLocal()
    try:
        positions = db.query(Position).filter(
            Position.subscription_id == sub_id,
            Position.status == "ACTIVE"
        ).all()
        assert len(positions) == 12

        folio = db.query(Folio).filter(Folio.id == 1).first()
        base_map = {s.ticker: s.base_quantity for s in folio.stocks}

        for p in positions:
            assert p.user_id == "user-pos-test"
            assert p.status == "ACTIVE"
            assert p.quantity == base_map[p.ticker] * 3.0
    finally:
        db.close()

def test_positions_updated_on_rebalance(client):
    # Subscribe user
    sub_res = client.post("/api/subscriptions", json={
        "user_id": "user-rebal-pos",
        "folio_id": 1,
        "multiplier": 2.0
    })
    sub_id = sub_res.json()["subscription"]["id"]

    # Rebalance: RELIANCE -> WIPRO (base qty 3.0)
    rebal_res = client.post("/api/admin/rebalance", json={
        "folio_id": 1,
        "outgoing_ticker": "RELIANCE",
        "incoming_ticker": "WIPRO",
        "new_base_quantity": 3.0
    })
    assert rebal_res.status_code == 202

    # Wait for rebalance worker
    for _ in range(30):
        q = client.get("/api/admin/queue").json()
        if q["pending_count"] == 0:
            break
        time.sleep(0.1)

    db = SessionLocal()
    try:
        # RELIANCE position should be liquidated
        rel_pos = db.query(Position).filter(
            Position.subscription_id == sub_id,
            Position.ticker == "RELIANCE"
        ).first()
        assert rel_pos is not None
        assert rel_pos.status == "LIQUIDATED"

        # WIPRO position should be ACTIVE with qty = 3.0 * 2.0 = 6.0
        wipro_pos = db.query(Position).filter(
            Position.subscription_id == sub_id,
            Position.ticker == "WIPRO",
            Position.status == "ACTIVE"
        ).first()
        assert wipro_pos is not None
        assert wipro_pos.quantity == 6.0

        # Total active positions should still be exactly 12
        active_pos_count = db.query(Position).filter(
            Position.subscription_id == sub_id,
            Position.status == "ACTIVE"
        ).count()
        assert active_pos_count == 12
    finally:
        db.close()

def test_positions_liquidated_on_exit(client):
    # Subscribe
    sub_res = client.post("/api/subscriptions", json={
        "user_id": "user-exit-pos",
        "folio_id": 1,
        "multiplier": 1.0
    })
    sub_id = sub_res.json()["subscription"]["id"]

    # Exit
    exit_res = client.post(f"/api/subscriptions/{sub_id}/exit")
    assert exit_res.status_code == 200

    db = SessionLocal()
    try:
        active_count = db.query(Position).filter(
            Position.subscription_id == sub_id,
            Position.status == "ACTIVE"
        ).count()
        assert active_count == 0

        liquidated_count = db.query(Position).filter(
            Position.subscription_id == sub_id,
            Position.status == "LIQUIDATED"
        ).count()
        assert liquidated_count == 12
    finally:
        db.close()
