import pytest
from sqlalchemy import create_engine, text, inspect
from app.db.database import run_migrations

def test_auto_migrations_on_legacy_schema(tmp_path):
    # 1. Create a legacy SQLite database file missing the new columns
    legacy_db_file = tmp_path / "legacy_test.db"
    legacy_engine = create_engine(f"sqlite:///{legacy_db_file}")

    with legacy_engine.begin() as conn:
        # Create legacy folios table (without version_id, is_rebalancing, rebalance_status)
        conn.execute(text("CREATE TABLE folios (id INTEGER PRIMARY KEY, name VARCHAR UNIQUE NOT NULL)"))
        # Create legacy orders table (without idempotency_key)
        conn.execute(text("CREATE TABLE orders (order_id VARCHAR PRIMARY KEY, user_id VARCHAR NOT NULL, ticker VARCHAR, action VARCHAR, quantity FLOAT, status VARCHAR, timestamp DATETIME)"))
        # Create legacy rebalance_tasks table (without next_retry_at)
        conn.execute(text("CREATE TABLE rebalance_tasks (id INTEGER PRIMARY KEY, folio_id INTEGER, subscription_id INTEGER, user_id VARCHAR, outgoing_ticker VARCHAR, incoming_ticker VARCHAR, multiplier FLOAT, outgoing_base_qty FLOAT, incoming_base_qty FLOAT, status VARCHAR, error_message VARCHAR, retries INTEGER, created_at DATETIME, completed_at DATETIME)"))

    # 2. Run auto-migrations
    run_migrations(legacy_engine)

    # 3. Verify all columns now exist
    inspector = inspect(legacy_engine)
    
    folio_cols = [c["name"] for c in inspector.get_columns("folios")]
    assert "version_id" in folio_cols
    assert "is_rebalancing" in folio_cols
    assert "rebalance_status" in folio_cols

    order_cols = [c["name"] for c in inspector.get_columns("orders")]
    assert "idempotency_key" in order_cols

    task_cols = [c["name"] for c in inspector.get_columns("rebalance_tasks")]
    assert "next_retry_at" in task_cols
