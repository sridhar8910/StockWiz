import time
import pytest
from app.db.database import SessionLocal
from app.models.rebalance_job import RebalanceJob
from app.models.rebalance_task import RebalanceTaskRecord

def test_rebalance_job_batch_creation_and_completion(client):
    # Setup 2 subscribers
    client.post("/api/subscriptions", json={"user_id": "user-job-1", "folio_id": 1, "multiplier": 1.0})
    client.post("/api/subscriptions", json={"user_id": "user-job-2", "folio_id": 1, "multiplier": 2.0})

    # Trigger rebalance
    res = client.post("/api/admin/rebalance", json={
        "folio_id": 1,
        "outgoing_ticker": "RELIANCE",
        "incoming_ticker": "GAIL",
        "new_base_quantity": 2.0
    })
    assert res.status_code == 202
    job_id = res.json()["job_id"]
    assert job_id is not None

    db = SessionLocal()
    try:
        job = db.query(RebalanceJob).filter(RebalanceJob.id == job_id).first()
        assert job is not None
        assert job.folio_id == 1
        assert job.outgoing_ticker == "RELIANCE"
        assert job.incoming_ticker == "GAIL"
        assert job.total_tasks == 2
        
        # Verify tasks are linked to this job_id
        tasks = db.query(RebalanceTaskRecord).filter(RebalanceTaskRecord.job_id == job_id).all()
        assert len(tasks) == 2
    finally:
        db.close()

    # Wait for completion
    for _ in range(30):
        q = client.get("/api/admin/queue").json()
        if q["pending_count"] == 0:
            break
        time.sleep(0.1)

    db = SessionLocal()
    try:
        job = db.query(RebalanceJob).filter(RebalanceJob.id == job_id).first()
        assert job.status == "COMPLETED"
        assert job.completed_tasks == 2
        assert job.completed_at is not None
    finally:
        db.close()
