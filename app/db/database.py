import os
import logging
from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.orm import sessionmaker, declarative_base

logger = logging.getLogger("database")

DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./stockwiz.db")

# check_same_thread=False and timeout for SQLite concurrent access
connect_args = {}
if DATABASE_URL.startswith("sqlite"):
    connect_args = {"check_same_thread": False, "timeout": 30}

engine = create_engine(
    DATABASE_URL,
    connect_args=connect_args,
    pool_pre_ping=True
)

# Enable WAL journal mode, foreign keys, and busy timeout for SQLite
@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    if DATABASE_URL.startswith("sqlite"):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys = ON")
        cursor.execute("PRAGMA journal_mode = WAL")
        cursor.execute("PRAGMA synchronous = NORMAL")
        cursor.execute("PRAGMA busy_timeout = 30000")
        cursor.close()

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def run_migrations(engine):
    """
    Safely apply schema migrations and unique indexes for database tables.
    Fails fast if a migration error occurs.
    """
    inspector = inspect(engine)
    table_names = inspector.get_table_names()
    is_sqlite = engine.dialect.name == "sqlite"
    
    try:
        with engine.begin() as conn:
            if "folios" in table_names:
                columns = [col["name"] for col in inspector.get_columns("folios")]
                if "version_id" not in columns:
                    conn.execute(text("ALTER TABLE folios ADD COLUMN version_id INTEGER DEFAULT 1 NOT NULL"))
                if "is_rebalancing" not in columns:
                    default_bool = "0" if is_sqlite else "FALSE"
                    conn.execute(text(f"ALTER TABLE folios ADD COLUMN is_rebalancing BOOLEAN DEFAULT {default_bool} NOT NULL"))
                if "rebalance_status" not in columns:
                    conn.execute(text("ALTER TABLE folios ADD COLUMN rebalance_status VARCHAR DEFAULT 'IDLE' NOT NULL"))
                    
            if "orders" in table_names:
                columns = [col["name"] for col in inspector.get_columns("orders")]
                if "idempotency_key" not in columns:
                    conn.execute(text("ALTER TABLE orders ADD COLUMN idempotency_key VARCHAR"))
                conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS uq_orders_idempotency_key ON orders(idempotency_key) WHERE idempotency_key IS NOT NULL"))

            if "rebalance_tasks" in table_names:
                columns = [col["name"] for col in inspector.get_columns("rebalance_tasks")]
                if "next_retry_at" not in columns:
                    conn.execute(text("ALTER TABLE rebalance_tasks ADD COLUMN next_retry_at DATETIME"))
                if "job_id" not in columns:
                    conn.execute(text("ALTER TABLE rebalance_tasks ADD COLUMN job_id INTEGER"))
                if "worker_id" not in columns:
                    conn.execute(text("ALTER TABLE rebalance_tasks ADD COLUMN worker_id VARCHAR"))
                if "claimed_at" not in columns:
                    conn.execute(text("ALTER TABLE rebalance_tasks ADD COLUMN claimed_at DATETIME"))
                if "lease_until" not in columns:
                    conn.execute(text("ALTER TABLE rebalance_tasks ADD COLUMN lease_until DATETIME"))

            if "subscriptions" in table_names:
                columns = [col["name"] for col in inspector.get_columns("subscriptions")]
                if "status" not in columns:
                    conn.execute(text("ALTER TABLE subscriptions ADD COLUMN status VARCHAR DEFAULT 'ACTIVE' NOT NULL"))
                active_clause = "active = 1" if is_sqlite else "active = TRUE"
                conn.execute(text(f"CREATE UNIQUE INDEX IF NOT EXISTS uq_active_user_folio ON subscriptions(user_id, folio_id) WHERE {active_clause}"))

            if "positions" in table_names:
                conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS uq_active_position ON positions(subscription_id, ticker) WHERE status = 'ACTIVE'"))
    except Exception as e:
        logger.exception(f"Migration failure during startup: {e}")
        raise e

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
