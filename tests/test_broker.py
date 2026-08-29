import pytest
from app.services.broker_service import BrokerService

def test_execute_trade_success():
    receipt = BrokerService.execute_trade(
        user_id="user-101",
        ticker="RELIANCE",
        action="BUY",
        quantity=6.0
    )
    
    assert receipt["status"] == "EXECUTED"
    assert receipt["order_id"].startswith("ord-")
    assert receipt["user_id"] == "user-101"
    assert receipt["ticker"] == "RELIANCE"
    assert receipt["action"] == "BUY"
    assert receipt["quantity"] == 6.0
    assert "timestamp" in receipt

def test_execute_trade_invalid_parameters():
    # Empty user_id
    with pytest.raises(ValueError, match="user_id is required"):
        BrokerService.execute_trade("", "RELIANCE", "BUY", 1.0)
        
    # Empty ticker
    with pytest.raises(ValueError, match="ticker is required"):
        BrokerService.execute_trade("user-101", "", "BUY", 1.0)
        
    # Invalid action
    with pytest.raises(ValueError, match="action must be BUY or SELL"):
        BrokerService.execute_trade("user-101", "RELIANCE", "HOLD", 1.0)
        
    # Negative quantity
    with pytest.raises(ValueError, match="quantity must be greater than zero"):
        BrokerService.execute_trade("user-101", "RELIANCE", "BUY", -5.0)
        
    # Zero quantity
    with pytest.raises(ValueError, match="quantity must be greater than zero"):
        BrokerService.execute_trade("user-101", "RELIANCE", "BUY", 0.0)

def test_broker_idempotency_same_key_returns_same_receipt():
    BrokerService.reset_cache()
    key = "idemp-test-12345"
    
    receipt1 = BrokerService.execute_trade("user-101", "INFY", "BUY", 5.0, idempotency_key=key)
    receipt2 = BrokerService.execute_trade("user-101", "INFY", "BUY", 5.0, idempotency_key=key)
    
    # Must return exact same order_id and receipt without duplicate execution
    assert receipt1["order_id"] == receipt2["order_id"]
    assert receipt1["timestamp"] == receipt2["timestamp"]

