import os
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, declarative_base

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

# Enable WAL journal mode for SQLite to support high concurrency
@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    if DATABASE_URL.startswith("sqlite"):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA busy_timeout=30000")
        cursor.close()

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def run_migrations(engine):
    """
    Safely apply lightweight SQLite schema migrations and indexes for existing database files.
    """
    from sqlalchemy import inspect, text
    inspector = inspect(engine)
    table_names = inspector.get_table_names()
    
    with engine.begin() as conn:
        if "folios" in table_names:
            columns = [col["name"] for col in inspector.get_columns("folios")]
            if "version_id" not in columns:
                conn.execute(text("ALTER TABLE folios ADD COLUMN version_id INTEGER DEFAULT 1 NOT NULL"))
            if "is_rebalancing" not in columns:
                conn.execute(text("ALTER TABLE folios ADD COLUMN is_rebalancing BOOLEAN DEFAULT 0 NOT NULL"))
            if "rebalance_status" not in columns:
                conn.execute(text("ALTER TABLE folios ADD COLUMN rebalance_status VARCHAR DEFAULT 'IDLE' NOT NULL"))
                
        if "orders" in table_names:
            columns = [col["name"] for col in inspector.get_columns("orders")]
            if "idempotency_key" not in columns:
                conn.execute(text("ALTER TABLE orders ADD COLUMN idempotency_key VARCHAR"))
            # Ensure unique index on idempotency_key
            try:
                conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS uq_orders_idempotency_key ON orders(idempotency_key) WHERE idempotency_key IS NOT NULL"))
            except Exception:
                pass

        if "rebalance_tasks" in table_names:
            columns = [col["name"] for col in inspector.get_columns("rebalance_tasks")]
            if "next_retry_at" not in columns:
                conn.execute(text("ALTER TABLE rebalance_tasks ADD COLUMN next_retry_at DATETIME"))
            if "job_id" not in columns:
                conn.execute(text("ALTER TABLE rebalance_tasks ADD COLUMN job_id INTEGER"))

        if "subscriptions" in table_names:
            try:
                conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS uq_active_user_folio ON subscriptions(user_id, folio_id) WHERE active = 1"))
            except Exception:
                pass

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
