import os
from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.db.database import engine, Base, SessionLocal, run_migrations
from app.db.seed import seed_data
from app.api.folios import router as folios_router
from app.api.subscriptions import router as subscriptions_router
from app.api.orders import router as orders_router
from app.api.admin import router as admin_router
from app.workers.rebalance_worker import rebalance_worker

# Compute absolute paths for assets to prevent CWD sensitivity
BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "static"
INDEX_HTML_PATH = STATIC_DIR / "index.html"

# OpenAPI Tag Metadata
tags_metadata = [
    {
        "name": "Folios",
        "description": "Browse and query curated **12-stock baskets** (Folios) with predefined base quantities and version tracking.",
    },
    {
        "name": "Subscriptions",
        "description": "User subscription lifecycle. Subscribe with configurable multipliers (`1x`, `2x`, `3x`, `5x`), generating **12 atomic BUY orders**, or exit to trigger **12 liquidating SELL orders**.",
    },
    {
        "name": "Orders",
        "description": "Audit trail of immutable execution receipts from the synthetic broker. Supports user search and real-time feed streaming.",
    },
    {
        "name": "Admin",
        "description": "Folio composition management and asynchronous rebalancing. Swap stocks inside a Folio and trigger **durable background fan-out cascades** to all active subscribers.",
    },
]

APP_DESCRIPTION = """
### 🚀 StockWiz — Basket-Trading & Auto-Rebalancing Trading System

StockWiz is a high-throughput, stateful basket-trading engine built with **FastAPI**, **SQLAlchemy**, and an **asynchronous durable worker queue**.

---

### 🔑 Core Architectural Features:
* **Curated 12-Stock Folios**: 7 distinct thematic equity baskets pre-seeded with strict domain invariants.
* **Proportional Position Sizing**: Order quantity is deterministically calculated as $\\text{Order Quantity} = \\text{Base Quantity} \\times \\text{User Multiplier}$.
* **Asynchronous Rebalancing Cascade**: Admin stock replacements return `202 Accepted` immediately, delegating execution to a durable worker.
* **Database-Backed Task Durability**: Background tasks are persisted in SQLite/PostgreSQL with automatic crash recovery across restarts.
* **True Broker Idempotency**: Trade executions check database idempotency keys before placement to guarantee at-least-once recovery without double-fills.
* **Optimistic Concurrency Protection**: Rebalancing operations lock the target Folio with `is_rebalancing` and bump `version_id`.
"""

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 1. Initialize DB schema & apply lightweight migrations
    Base.metadata.create_all(bind=engine)
    run_migrations(engine)
    
    # 2. Seed data with validation
    db = SessionLocal()
    try:
        seed_data(db)
    finally:
        db.close()
        
    # 3. Start durable background rebalance worker (recovers any pending DB tasks)
    rebalance_worker.start()
    
    yield
    
    # 4. Stop background worker cleanly on shutdown
    await rebalance_worker.stop()

app = FastAPI(
    title="StockWiz API — Basket-Trading & Auto-Rebalancing System",
    description=APP_DESCRIPTION,
    version="1.0.0",
    openapi_tags=tags_metadata,
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan
)

# Standardize RequestValidationError to return HTTP 400 Bad Request per Spec Section 18
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    errors = exc.errors()
    error_messages = []
    for err in errors:
        loc = " -> ".join(str(l) for l in err.get("loc", []) if l != "body")
        msg = err.get("msg", "Invalid input")
        error_messages.append(f"{loc}: {msg}" if loc else msg)
    return JSONResponse(
        status_code=400,
        content={"detail": "; ".join(error_messages)}
    )

# Register routers
app.include_router(folios_router)
app.include_router(subscriptions_router)
app.include_router(orders_router)
app.include_router(admin_router)

# Ensure static folder exists
os.makedirs(STATIC_DIR, exist_ok=True)

# Serve Frontend at Root
@app.get("/", include_in_schema=False)
def get_frontend():
    return FileResponse(INDEX_HTML_PATH)

# Also mount the static folder
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
