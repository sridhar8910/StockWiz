import os
from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.responses import FileResponse
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

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 1. Initialize DB schema & apply lightweight SQLite migrations
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
    title="StockWiz Folio Trading & Auto-Rebalancing System",
    description="Senior Full-Stack Developer Assessment Prototype",
    version="1.0.0",
    lifespan=lifespan
)

# Register routers
app.include_router(folios_router)
app.include_router(subscriptions_router)
app.include_router(orders_router)
app.include_router(admin_router)

# Ensure static folder exists
os.makedirs(STATIC_DIR, exist_ok=True)

# Serve Frontend at Root
@app.get("/")
def get_frontend():
    return FileResponse(INDEX_HTML_PATH)

# Also mount the static folder
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
