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

def test_multi_worker_atomic_task_claim_race(client):
    from sqlalchemy import text
    from app.models.rebalance_task import RebalanceTaskRecord

    # Create a pending task in DB
    db1 = SessionLocal()
    try:
        task = RebalanceTaskRecord(
            folio_id=1,
            subscription_id=1,
            user_id="user-race",
            outgoing_ticker="RELIANCE",
            incoming_ticker="WIPRO",
            multiplier=1.0,
            outgoing_base_qty=2.0,
            incoming_base_qty=2.0,
            status="PENDING"
        )
        db1.add(task)
        db1.commit()
        task_id = task.id
    finally:
        db1.close()

    # Simulate Worker 1 and Worker 2 racing to claim the same task
    db_worker1 = SessionLocal()
    db_worker2 = SessionLocal()
    try:
        claim_sql = text("UPDATE rebalance_tasks SET status = 'PROCESSING' WHERE id = :id AND status = 'PENDING'")
        
        # Worker 1 executes claim
        res1 = db_worker1.execute(claim_sql, {"id": task_id})
        db_worker1.commit()
        
        # Worker 2 attempts same claim
        res2 = db_worker2.execute(claim_sql, {"id": task_id})
        db_worker2.commit()

        # Exactly one worker wins the atomic row claim
        assert res1.rowcount == 1
        assert res2.rowcount == 0
    finally:
        db_worker1.close()
        db_worker2.close()

