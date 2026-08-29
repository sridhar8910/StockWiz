import time
import pytest
from app.db.database import SessionLocal
from app.models.folio import Folio
from app.models.subscription import Subscription
from app.models.rebalance_task import RebalanceTaskRecord
from app.models.order import Order
from app.workers.rebalance_worker import rebalance_worker

def test_durable_worker_processes_pending_tasks(client):
    # 1. Setup subscription
    client.post("/api/subscriptions", json={"user_id": "user-durable", "folio_id": 1, "multiplier": 2.0})

    # 2. Trigger rebalance
    res = client.post("/api/admin/rebalance", json={
        "folio_id": 1,
        "outgoing_ticker": "RELIANCE",
        "incoming_ticker": "WIPRO",
        "new_base_quantity": 3.0
    })
    assert res.status_code == 202

    # Verify task row exists in DB
    db = SessionLocal()
    try:
        tasks = db.query(RebalanceTaskRecord).filter(RebalanceTaskRecord.user_id == "user-durable").all()
        assert len(tasks) == 1
        assert tasks[0].outgoing_ticker == "RELIANCE"
        assert tasks[0].incoming_ticker == "WIPRO"
    finally:
        db.close()

    # Wait for completion
    for _ in range(30):
        m = client.get("/api/admin/queue").json()
        if m["pending_count"] == 0:
            break
        time.sleep(0.1)

    db = SessionLocal()
    try:
        task = db.query(RebalanceTaskRecord).filter(RebalanceTaskRecord.user_id == "user-durable").first()
        assert task.status == "COMPLETED"
        assert task.completed_at is not None
    finally:
        db.close()

def test_durable_worker_crash_recovery(client):
    # Setup subscription
    client.post("/api/subscriptions", json={"user_id": "user-crash-test", "folio_id": 2, "multiplier": 1.0})
    sub_id = client.get("/api/users/user-crash-test/subscriptions").json()[0]["id"]

    # Directly insert a task with status 'PROCESSING' (simulating server crash mid-execution)
    db = SessionLocal()
    try:
        crashed_task = RebalanceTaskRecord(
            folio_id=2,
            subscription_id=sub_id,
            user_id="user-crash-test",
            outgoing_ticker="RELIANCE",
            incoming_ticker="GAIL",
            multiplier=1.0,
            outgoing_base_qty=3.0,
            incoming_base_qty=3.0,
            status="PROCESSING"
        )
        db.add(crashed_task)
        db.commit()
        task_id = crashed_task.id
    finally:
        db.close()

    # Trigger recovery directly
    rebalance_worker._recover_stuck_tasks()

    # Verify task was recovered to PENDING
    db = SessionLocal()
    try:
        t = db.query(RebalanceTaskRecord).filter(RebalanceTaskRecord.id == task_id).first()
        assert t.status == "PENDING"
    finally:
        db.close()

    # Notify worker and wait for execution
    rebalance_worker.notify()
    for _ in range(30):
        m = client.get("/api/admin/queue").json()
        if m["pending_count"] == 0:
            break
        time.sleep(0.1)

    db = SessionLocal()
    try:
        t = db.query(RebalanceTaskRecord).filter(RebalanceTaskRecord.id == task_id).first()
        assert t.status == "COMPLETED"
    finally:
        db.close()
