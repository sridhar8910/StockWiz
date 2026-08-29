import time
import pytest
from app.db.database import SessionLocal
from app.models.folio import Folio
from app.models.order import Order
from app.models.subscription import Subscription

def test_admin_rebalance_cascade(client):
    # Setup subscribers for Folio 1 (Alpha Growth)
    
    # 1. User A (active, multiplier 1x)
    subA = client.post("/api/subscriptions", json={"user_id": "user-A", "folio_id": 1, "multiplier": 1.0}).json()["subscription"]
    
    # 2. User B (active, multiplier 3x)
    subB = client.post("/api/subscriptions", json={"user_id": "user-B", "folio_id": 1, "multiplier": 3.0}).json()["subscription"]
    
    # 3. User C (active, multiplier 5x)
    subC = client.post("/api/subscriptions", json={"user_id": "user-C", "folio_id": 1, "multiplier": 5.0}).json()["subscription"]
    
    # 4. User D (inactive, multiplier 2x - we subscribe then exit)
    subD_setup = client.post("/api/subscriptions", json={"user_id": "user-D", "folio_id": 1, "multiplier": 2.0}).json()["subscription"]
    client.post(f"/api/subscriptions/{subD_setup['id']}/exit")
    
    # Get initial base quantity of RELIANCE in Folio 1
    db = SessionLocal()
    try:
        folio = db.query(Folio).filter(Folio.id == 1).first()
        reliance_stock = next(s for s in folio.stocks if s.ticker == "RELIANCE")
        reliance_base_qty = reliance_stock.base_quantity
        assert reliance_base_qty == 2.0
    finally:
        db.close()

    # Trigger admin rebalance: RELIANCE -> IDEA with new base quantity 4.0
    rebalance_payload = {
        "folio_id": 1,
        "outgoing_ticker": "RELIANCE",
        "incoming_ticker": "IDEA",
        "new_base_quantity": 4.0
    }
    
    rebalance_res = client.post("/api/admin/rebalance", json=rebalance_payload)
    assert rebalance_res.status_code == 202
    res_data = rebalance_res.json()
    assert res_data["outgoing_ticker"] == "RELIANCE"
    assert res_data["incoming_ticker"] == "IDEA"
    # User A, B, C are active, User D is inactive. So exactly 3 subscribers are queued.
    assert res_data["active_subscribers_queued"] == 3

    # Wait for the background worker queue to empty
    success = False
    for _ in range(30):  # poll for up to 3 seconds
        queue_status = client.get("/api/admin/queue").json()
        if queue_status["pending_count"] == 0:
            success = True
            break
        time.sleep(0.1)
    
    assert success is True, "Background worker timed out processing rebalance tasks"

    # Verify database composition updated
    db = SessionLocal()
    try:
        updated_folio = db.query(Folio).filter(Folio.id == 1).first()
        # RELIANCE should be gone
        assert not any(s.ticker == "RELIANCE" for s in updated_folio.stocks)
        # IDEA should be present with base quantity 4.0
        idea_stock = next(s for s in updated_folio.stocks if s.ticker == "IDEA")
        assert idea_stock.base_quantity == 4.0
        assert len(updated_folio.stocks) == 12

        # Verify User A (1x multiplier) got: SELL RELIANCE * 2, BUY IDEA * 4
        orders_A = db.query(Order).filter(Order.user_id == "user-A", Order.subscription_id == subA["id"]).all()
        # User A has 12 BUY orders from subscribe + 1 SELL + 1 BUY from rebalance = 14 orders total
        assert len(orders_A) == 14
        
        sell_rel_A = db.query(Order).filter(Order.user_id == "user-A", Order.ticker == "RELIANCE", Order.action == "SELL").first()
        assert sell_rel_A is not None
        assert sell_rel_A.quantity == reliance_base_qty * 1.0  # 2.0 * 1.0 = 2.0
        
        buy_idea_A = db.query(Order).filter(Order.user_id == "user-A", Order.ticker == "IDEA", Order.action == "BUY").first()
        assert buy_idea_A is not None
        assert buy_idea_A.quantity == 4.0 * 1.0  # 4.0 * 1.0 = 4.0

        # Verify User B (3x multiplier) got: SELL RELIANCE * 6, BUY IDEA * 12
        sell_rel_B = db.query(Order).filter(Order.user_id == "user-B", Order.ticker == "RELIANCE", Order.action == "SELL").first()
        assert sell_rel_B is not None
        assert sell_rel_B.quantity == reliance_base_qty * 3.0  # 2.0 * 3.0 = 6.0
        
        buy_idea_B = db.query(Order).filter(Order.user_id == "user-B", Order.ticker == "IDEA", Order.action == "BUY").first()
        assert buy_idea_B is not None
        assert buy_idea_B.quantity == 4.0 * 3.0  # 4.0 * 3.0 = 12.0

        # Verify User C (5x multiplier) got: SELL RELIANCE * 10, BUY IDEA * 20
        sell_rel_C = db.query(Order).filter(Order.user_id == "user-C", Order.ticker == "RELIANCE", Order.action == "SELL").first()
        assert sell_rel_C is not None
        assert sell_rel_C.quantity == reliance_base_qty * 5.0  # 2.0 * 5.0 = 10.0
        
        buy_idea_C = db.query(Order).filter(Order.user_id == "user-C", Order.ticker == "IDEA", Order.action == "BUY").first()
        assert buy_idea_C is not None
        assert buy_idea_C.quantity == 4.0 * 5.0  # 4.0 * 5.0 = 20.0

        # Verify User D (inactive) received NO rebalance orders (i.e. only 1 exit SELL, and no BUY IDEA)
        sell_rel_D_count = db.query(Order).filter(Order.user_id == "user-D", Order.ticker == "RELIANCE", Order.action == "SELL").count()
        assert sell_rel_D_count == 1  # 1 from exit, 0 from rebalance
        
        buy_idea_D = db.query(Order).filter(Order.user_id == "user-D", Order.ticker == "IDEA", Order.action == "BUY").first()
        assert buy_idea_D is None
    finally:
        db.close()

def test_section_27_expected_end_to_end_scenario(client):
    """
    Directly tests the multi-step reviewer scenario specified in Section 27 of the assessment:
    1. user-101 subscribes to Alpha Growth (3x)
    2. 12 BUY orders created (qty = base * 3)
    3. user-202 subscribes to Alpha Growth (5x)
    4. Admin swaps RELIANCE -> IDEA
    5. Admin API responds immediately (HTTP 202)
    6. Background worker processes user-101 (qty=6) and user-202 (qty=10)
    7. user-101 exits folio (12 SELL orders executed, including IDEA, excluding RELIANCE)
    8. user-202 remains active
    9. All execution receipts visible in orders feed
    """
    # 1. user-101 subscribes to Alpha Growth with 3x multiplier
    sub1_res = client.post("/api/subscriptions", json={
        "user_id": "user-101",
        "folio_id": 1,
        "multiplier": 3.0
    })
    assert sub1_res.status_code == 201
    sub1_data = sub1_res.json()
    sub1_id = sub1_data["subscription"]["id"]
    
    # 2. Verify 12 BUY orders created with qty = Base Quantity * 3
    orders1 = sub1_data["orders"]
    assert len(orders1) == 12
    db = SessionLocal()
    try:
        folio1 = db.query(Folio).filter(Folio.id == 1).first()
        base_map = {s.ticker: s.base_quantity for s in folio1.stocks}
        for o in orders1:
            assert o["action"] == "BUY"
            assert o["quantity"] == base_map[o["ticker"]] * 3.0
    finally:
        db.close()

    # 3. user-202 subscribes to same Folio with 5x multiplier
    sub2_res = client.post("/api/subscriptions", json={
        "user_id": "user-202",
        "folio_id": 1,
        "multiplier": 5.0
    })
    assert sub2_res.status_code == 201
    sub2_id = sub2_res.json()["subscription"]["id"]

    # 4. Admin replaces RELIANCE with IDEA (base quantity = 2.0)
    rebal_res = client.post("/api/admin/rebalance", json={
        "folio_id": 1,
        "outgoing_ticker": "RELIANCE",
        "incoming_ticker": "IDEA",
        "new_base_quantity": 2.0
    })
    assert rebal_res.status_code == 202
    assert rebal_res.json()["active_subscribers_queued"] == 2

    # 5. Wait for background worker cascade to process
    for _ in range(30):
        q = client.get("/api/admin/queue").json()
        if q["pending_count"] == 0:
            break
        time.sleep(0.1)

    db = SessionLocal()
    try:
        # Verify user-101 rebalance receipts: SELL RELIANCE * 6, BUY IDEA * 6
        u101_sell_rel = db.query(Order).filter(Order.user_id == "user-101", Order.ticker == "RELIANCE", Order.action == "SELL").first()
        assert u101_sell_rel is not None
        assert u101_sell_rel.quantity == 2.0 * 3.0  # 6.0
        
        u101_buy_idea = db.query(Order).filter(Order.user_id == "user-101", Order.ticker == "IDEA", Order.action == "BUY").first()
        assert u101_buy_idea is not None
        assert u101_buy_idea.quantity == 2.0 * 3.0  # 6.0

        # Verify user-202 rebalance receipts: SELL RELIANCE * 10, BUY IDEA * 10
        u202_sell_rel = db.query(Order).filter(Order.user_id == "user-202", Order.ticker == "RELIANCE", Order.action == "SELL").first()
        assert u202_sell_rel is not None
        assert u202_sell_rel.quantity == 2.0 * 5.0  # 10.0
        
        u202_buy_idea = db.query(Order).filter(Order.user_id == "user-202", Order.ticker == "IDEA", Order.action == "BUY").first()
        assert u202_buy_idea is not None
        assert u202_buy_idea.quantity == 2.0 * 5.0  # 10.0
    finally:
        db.close()

    # 6. Exit user-101's Folio
    exit_res = client.post(f"/api/subscriptions/{sub1_id}/exit")
    assert exit_res.status_code == 200
    exit_orders = exit_res.json()["orders"]
    assert len(exit_orders) == 12
    exit_tickers = {o["ticker"] for o in exit_orders}
    assert "IDEA" in exit_tickers
    assert "RELIANCE" not in exit_tickers

    # 7. Verify user-202 remains active
    subs_u202 = client.get("/api/users/user-202/subscriptions").json()
    active_202 = [s for s in subs_u202 if s["id"] == sub2_id and s["active"] is True]
    assert len(active_202) == 1

    # 8. Verify execution receipts visible in order feed
    orders_feed = client.get("/api/orders?limit=100").json()
    # 12 (sub1) + 12 (sub2) + 2 (rebalance1) + 2 (rebalance2) + 12 (exit1) = 40 orders
    assert len(orders_feed) == 40

