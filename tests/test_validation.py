import pytest

def test_validation_subscribe_invalid_folio(client):
    # Non-existent folio
    payload = {
        "user_id": "user-101",
        "folio_id": 9999,  # does not exist
        "multiplier": 3.0
    }
    response = client.post("/api/subscriptions", json=payload)
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()

def test_validation_subscribe_invalid_multiplier(client):
    # Negative multiplier -> 400 Bad Request per Spec Section 18
    payload = {
        "user_id": "user-101",
        "folio_id": 1,
        "multiplier": -1.5
    }
    response = client.post("/api/subscriptions", json=payload)
    assert response.status_code == 400
    assert "greater than 0" in response.json()["detail"]

    # Zero multiplier -> 400 Bad Request per Spec Section 18
    payload["multiplier"] = 0
    response = client.post("/api/subscriptions", json=payload)
    assert response.status_code == 400
    assert "greater than 0" in response.json()["detail"]

def test_validation_subscribe_empty_user_id(client):
    # Empty string user_id -> 400 Bad Request
    payload = {
        "user_id": "",
        "folio_id": 1,
        "multiplier": 1.0
    }
    response = client.post("/api/subscriptions", json=payload)
    assert response.status_code == 400

    # Whitespace-only user_id -> 400 Bad Request
    payload["user_id"] = "   "
    response = client.post("/api/subscriptions", json=payload)
    assert response.status_code == 400

def test_validation_rebalance_invalid_folio(client):
    payload = {
        "folio_id": 9999,  # does not exist
        "outgoing_ticker": "RELIANCE",
        "incoming_ticker": "IDEA"
    }
    response = client.post("/api/admin/rebalance", json=payload)
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()

def test_validation_rebalance_missing_outgoing_ticker(client):
    # Ticker that does not exist in the folio
    payload = {
        "folio_id": 1,
        "outgoing_ticker": "NONEXISTENT",
        "incoming_ticker": "IDEA"
    }
    response = client.post("/api/admin/rebalance", json=payload)
    assert response.status_code == 400
    assert "does not exist in Folio" in response.json()["detail"]

def test_validation_rebalance_duplicate_incoming_ticker(client):
    # TCS already exists in Alpha Growth, so we can't swap RELIANCE -> TCS
    payload = {
        "folio_id": 1,
        "outgoing_ticker": "RELIANCE",
        "incoming_ticker": "TCS"
    }
    response = client.post("/api/admin/rebalance", json=payload)
    assert response.status_code == 400
    assert "already exists in Folio" in response.json()["detail"]

def test_validation_rebalance_invalid_base_quantity(client):
    payload = {
        "folio_id": 1,
        "outgoing_ticker": "RELIANCE",
        "incoming_ticker": "IDEA",
        "new_base_quantity": -3.5
    }
    response = client.post("/api/admin/rebalance", json=payload)
    assert response.status_code == 400
    assert "greater than 0" in response.json()["detail"]
