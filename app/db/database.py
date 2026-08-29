import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./stockwiz.db")

# check_same_thread=False is needed only for SQLite
connect_args = {}
if DATABASE_URL.startswith("sqlite"):
    connect_args = {"check_same_thread": False}

engine = create_engine(
    DATABASE_URL,
    connect_args=connect_args,
    pool_pre_ping=True
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def run_migrations(engine):
    """
    Safely apply lightweight SQLite schema migrations for existing database files.
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
                
        if "orders" in table_names:
            columns = [col["name"] for col in inspector.get_columns("orders")]
            if "idempotency_key" not in columns:
                conn.execute(text("ALTER TABLE orders ADD COLUMN idempotency_key VARCHAR"))

        if "rebalance_tasks" in table_names:
            columns = [col["name"] for col in inspector.get_columns("rebalance_tasks")]
            if "next_retry_at" not in columns:
                conn.execute(text("ALTER TABLE rebalance_tasks ADD COLUMN next_retry_at DATETIME"))

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
