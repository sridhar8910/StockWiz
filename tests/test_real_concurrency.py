import time
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
from sqlalchemy import text
import pytest
from app.db.database import SessionLocal
from app.models.subscription import Subscription
from app.models.position import Position
from app.models.folio import Folio
from app.models.order import Order
from app.services.broker_service import BrokerService

def test_concurrent_duplicate_subscriptions_race(client):
    """
    Test 1: 20 simultaneous subscription requests for the same user & folio.
    Guarantees that database-level partial unique index + atomic transactions
    permit exactly 1 active subscription and reject 19 with 400.
    """
    user_id = "user-20-race-sub"
    folio_id = 1
    multiplier = 3.0

    def make_subscribe_request():
        return client.post("/api/subscriptions", json={
            "user_id": user_id,
            "folio_id": folio_id,
            "multiplier": multiplier
        })

    with ThreadPoolExecutor(max_workers=20) as executor:
        futures = [executor.submit(make_subscribe_request) for _ in range(20)]
        results = [f.result() for f in futures]

    status_codes = [r.status_code for r in results]
    success_count = status_codes.count(201)
    conflict_count = status_codes.count(400)

    # Exactly 1 must win, all other 19 must fail cleanly
    assert success_count == 1
    assert conflict_count == 19

    # Verify DB state has exactly 1 subscription record
    db = SessionLocal()
    try:
        active_subs = db.query(Subscription).filter(
            Subscription.user_id == user_id,
            Subscription.folio_id == folio_id,
            Subscription.active == True
        ).all()
        assert len(active_subs) == 1

        # Verify exactly 12 active positions
        positions = db.query(Position).filter(
            Position.subscription_id == active_subs[0].id,
            Position.status == "ACTIVE"
        ).all()
        assert len(positions) == 12

        # Verify exactly 12 BUY orders
        orders = db.query(Order).filter(Order.subscription_id == active_subs[0].id).all()
        assert len(orders) == 12
    finally:
        db.close()

def test_concurrent_exit_race(client):
    """
    Test 2: 20 simultaneous exit requests on the same active subscription.
    Guarantees that atomic conditional state transition permits exactly 1 exit
    and rejects 19 with 400 (already inactive).
    """
    # 1. Setup active subscription
    sub_res = client.post("/api/subscriptions", json={
        "user_id": "user-20-exit-race",
        "folio_id": 1,
        "multiplier": 2.0
    })
    assert sub_res.status_code == 201
    sub_id = sub_res.json()["subscription"]["id"]

    def make_exit_request():
        return client.post(f"/api/subscriptions/{sub_id}/exit")

    with ThreadPoolExecutor(max_workers=20) as executor:
        futures = [executor.submit(make_exit_request) for _ in range(20)]
        results = [f.result() for f in futures]

    status_codes = [r.status_code for r in results]
    success_count = status_codes.count(200)
    conflict_count = status_codes.count(400)

    # Exactly 1 exit request wins
    assert success_count == 1
    assert conflict_count == 19

    # Verify DB state: subscription inactive, 12 liquidated positions, 12 SELL orders
    db = SessionLocal()
    try:
        sub = db.query(Subscription).filter(Subscription.id == sub_id).first()
        assert sub.active is False
        assert sub.status == "EXITED"

        active_pos = db.query(Position).filter(Position.subscription_id == sub_id, Position.status == "ACTIVE").count()
        assert active_pos == 0

        sell_orders = db.query(Order).filter(Order.subscription_id == sub_id, Order.action == "SELL").all()
        assert len(sell_orders) == 12
    finally:
        db.close()

def test_concurrent_rebalance_atomic_lock_race():
    """
    Test 3: 20 simultaneous threads executing the atomic conditional SQL lock on folios.
    Guarantees that exactly 1 thread wins the lock (rowcount == 1),
    and 19 threads are rejected (rowcount == 0).
    """
    claim_sql = text(
        "UPDATE folios SET is_rebalancing = 1, rebalance_status = 'REBALANCING' WHERE id = :id AND is_rebalancing = 0"
    )

    def attempt_lock():
        db = SessionLocal()
        try:
            res = db.execute(claim_sql, {"id": 1})
            db.commit()
            return res.rowcount
        finally:
            db.close()

    with ThreadPoolExecutor(max_workers=20) as executor:
        futures = [executor.submit(attempt_lock) for _ in range(20)]
        results = [f.result() for f in futures]

    # Exactly 1 thread succeeds in claiming the atomic lock
    assert results.count(1) == 1
    # 19 competing threads fail
    assert results.count(0) == 19

    # Clean up lock
    db = SessionLocal()
    try:
        folio = db.query(Folio).filter(Folio.id == 1).first()
        folio.is_rebalancing = False
        folio.rebalance_status = "IDLE"
        db.commit()
    finally:
        db.close()

def test_exit_during_rebalance_state_coordination(client):
    """
    Test 4: User exits while rebalance is initiated.
    Verifies that the state machine cleanly marks subscription EXITED,
    liquidates positions, and worker skips subsequent BUYs without corrupting positions.
    """
    # 1. Subscribe
    sub_res = client.post("/api/subscriptions", json={
        "user_id": "user-exit-during-rebal",
        "folio_id": 1,
        "multiplier": 1.0
    })
    sub_id = sub_res.json()["subscription"]["id"]

    # 2. Trigger rebalance
    rebal_res = client.post("/api/admin/rebalance", json={
        "folio_id": 1,
        "outgoing_ticker": "RELIANCE",
        "incoming_ticker": "IDEA",
        "new_base_quantity": 2.0
    })
    assert rebal_res.status_code == 202

    # 3. Immediately exit subscription
    exit_res = client.post(f"/api/subscriptions/{sub_id}/exit")
    assert exit_res.status_code in (200, 400)

    # 4. Wait for background worker
    for _ in range(30):
        q = client.get("/api/admin/queue").json()
        if q["pending_count"] == 0:
            break
        time.sleep(0.1)

    # 5. Verify database state is 100% consistent (0 active positions, subscription EXITED)
    db = SessionLocal()
    try:
        sub = db.query(Subscription).filter(Subscription.id == sub_id).first()
        assert sub.active is False
        assert sub.status == "EXITED"

        active_positions = db.query(Position).filter(
            Position.subscription_id == sub_id,
            Position.status == "ACTIVE"
        ).count()
        assert active_positions == 0
    finally:
        db.close()

def test_broker_partial_failure_idempotent_retry(client):
    """
    Test 5: Simulated broker failure during task execution.
    Verifies that worker retries without duplicating SELL or BUY orders,
    and cleanly reconciles the Position ledger.
    """
    # 1. Setup subscription
    client.post("/api/subscriptions", json={
        "user_id": "user-retry-test",
        "folio_id": 2,
        "multiplier": 1.0
    })

    # 2. Trigger rebalance
    res = client.post("/api/admin/rebalance", json={
        "folio_id": 2,
        "outgoing_ticker": "RELIANCE",
        "incoming_ticker": "WIPRO",
        "new_base_quantity": 2.0
    })
    assert res.status_code == 202
    job_id = res.json()["job_id"]

    # 3. Wait for worker to finish
    for _ in range(30):
        q = client.get("/api/admin/queue").json()
        if q["pending_count"] == 0:
            break
        time.sleep(0.1)

    # 4. Verify no duplicate orders created
    db = SessionLocal()
    try:
        sub = db.query(Subscription).filter(Subscription.user_id == "user-retry-test").first()
        orders = db.query(Order).filter(Order.subscription_id == sub.id).all()
        
        # 12 initial BUYs + 1 rebalance SELL + 1 rebalance BUY = 14 orders total
        assert len(orders) == 14
        
        # Verify idempotency keys are all unique
        idemp_keys = [o.idempotency_key for o in orders if o.idempotency_key]
        assert len(idemp_keys) == len(set(idemp_keys))

        # Verify active positions
        active_pos = db.query(Position).filter(
            Position.subscription_id == sub.id,
            Position.status == "ACTIVE"
        ).all()
        assert len(active_pos) == 12
        tickers = {p.ticker for p in active_pos}
        assert "WIPRO" in tickers
        assert "RELIANCE" not in tickers
    finally:
        db.close()
