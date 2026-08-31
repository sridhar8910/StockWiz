import time
from concurrent.futures import ThreadPoolExecutor
from sqlalchemy import text
import pytest
from app.db.database import SessionLocal
from app.models.subscription import Subscription
from app.models.position import Position
from app.models.folio import Folio

def test_concurrent_duplicate_subscriptions_race(client):
    """
    Spawns 10 concurrent threads attempting to subscribe the same user
    to the same Folio simultaneously via HTTP API.
    Guarantees that database-level partial unique index + atomic transactions
    permit exactly 1 active subscription and reject 9 with 400.
    """
    user_id = "user-concurrent-sub"
    folio_id = 1
    multiplier = 2.0

    def make_subscribe_request():
        return client.post("/api/subscriptions", json={
            "user_id": user_id,
            "folio_id": folio_id,
            "multiplier": multiplier
        })

    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(make_subscribe_request) for _ in range(10)]
        results = [f.result() for f in futures]

    status_codes = [r.status_code for r in results]
    success_count = status_codes.count(201)
    conflict_count = status_codes.count(400)

    # Exactly 1 must win, all other 9 must fail cleanly
    assert success_count == 1
    assert conflict_count == 9

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
    finally:
        db.close()

def test_concurrent_rebalance_atomic_lock_race():
    """
    Spawns 10 concurrent worker threads executing the atomic SQL conditional
    rebalance lock on the database simultaneously.
    Guarantees that exactly 1 thread wins the lock (rowcount == 1),
    and 9 threads are rejected (rowcount == 0).
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

    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(attempt_lock) for _ in range(10)]
        results = [f.result() for f in futures]

    # Exactly 1 thread succeeds in claiming the atomic lock
    assert results.count(1) == 1
    # 9 competing threads fail
    assert results.count(0) == 9

    # Clean up lock
    db = SessionLocal()
    try:
        folio = db.query(Folio).filter(Folio.id == 1).first()
        folio.is_rebalancing = False
        folio.rebalance_status = "IDLE"
        db.commit()
    finally:
        db.close()
