import pytest
from unittest.mock import patch
from app.db.database import SessionLocal
from app.models.subscription import Subscription
from app.models.order import Order
from app.services.broker_service import BrokerService

def test_subscribe_atomicity_rollback_on_broker_failure(client):
    # Mock BrokerService.execute_trade to fail on the 6th stock
    call_count = 0
    def mock_failing_trade(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count >= 6:
            raise RuntimeError("Simulated broker network timeout")
        return {
            "order_id": f"ord-mock-{call_count}",
            "status": "EXECUTED",
            "timestamp": "2026-08-22T12:00:00Z",
            "user_id": args[0] if args else kwargs.get("user_id"),
            "ticker": args[1] if len(args) > 1 else kwargs.get("ticker"),
            "action": args[2] if len(args) > 2 else kwargs.get("action"),
            "quantity": args[3] if len(args) > 3 else kwargs.get("quantity")
        }

    with patch("app.services.subscription_service.BrokerService.execute_trade", side_effect=mock_failing_trade):
        with pytest.raises(Exception):
            client.post("/api/subscriptions", json={
                "user_id": "user-atomic-test",
                "folio_id": 1,
                "multiplier": 1.0
            })

    # Verify no partial subscription was committed to DB
    db = SessionLocal()
    try:
        sub = db.query(Subscription).filter(Subscription.user_id == "user-atomic-test").first()
        assert sub is None

        # Verify no orphan orders were saved
        orders = db.query(Order).filter(Order.user_id == "user-atomic-test").all()
        assert len(orders) == 0
    finally:
        db.close()
