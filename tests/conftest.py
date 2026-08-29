import os
import time

# Force the application to use a test database file
os.environ["DATABASE_URL"] = "sqlite:///./test_stockwiz.db"

import pytest
from fastapi.testclient import TestClient
from app.db.database import Base, engine, SessionLocal
from app.db.seed import seed_data
from app.main import app

@pytest.fixture(scope="session", autouse=True)
def clean_test_db_before_and_after():
    # Remove test DB file if leftover
    if os.path.exists("./test_stockwiz.db"):
        try:
            os.remove("./test_stockwiz.db")
        except PermissionError:
            pass
            
    yield
    
    # Clean up test DB file after session
    if os.path.exists("./test_stockwiz.db"):
        try:
            os.remove("./test_stockwiz.db")
        except PermissionError:
            pass

@pytest.fixture(name="db", autouse=True)
def fixture_db():
    # Setup tables
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    
    db = SessionLocal()
    seed_data(db)
    db.close()
    
    yield
    
    # Cleanup after test
    Base.metadata.drop_all(bind=engine)

@pytest.fixture(name="client")
def fixture_client():
    # Use TestClient as context manager to execute FastAPI lifespan events (start background worker)
    with TestClient(app) as c:
        yield c
