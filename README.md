# StockWiz — Basket-Trading & Auto-Rebalancing System

StockWiz is a stateful basket-trading engine built with **FastAPI**, **SQLAlchemy**, and an **asynchronous durable worker queue**. 

Users can subscribe to curated stock bundles called **Folios** (each containing exactly 12 stocks) with a quantity multiplier (e.g., `1x`, `2x`, `3x`, `5x`). Administrators can replace stocks inside a Folio, and the system automatically cascades the changes to all active subscribers of that Folio asynchronously with atomic concurrency protection, per-user position tracking, and full worker durability.

---

## 1. Setup & Installation

### Prerequisites
- Python 3.10+ installed and on your system path.

### Step 1: Clone and Navigate to Directory
```bash
cd StockWiz
```

### Step 2: Install Dependencies
```bash
pip install -r requirements.txt
```

### Step 3: Run the Application
Start the Uvicorn development server:
```bash
python -m uvicorn app.main:app --reload
```

The application will start on `http://127.0.0.1:8000`.
- **Frontend Dashboard**: Open `http://127.0.0.1:8000/` in your browser.
- **FastAPI Swagger Docs**: Open `http://127.0.0.1:8000/docs` in your browser.

---

## 2. Architecture & Concurrency Design

```mermaid
flowchart LR
    User["User Dashboard"]
    Admin["Admin Terminal"]
    UI["HTML / JS Frontend"]
    API["FastAPI API Layer"]
    Worker["Durable DB-Backed Worker"]
    DB[("Database\n(positions / rebalance_jobs / folios / orders)")]
    Broker["Simulated Broker"]

    User --> UI
    Admin --> UI
    UI --> API
    API --> DB
    API --> Worker
    Worker --> DB
    Worker --> Broker
    API --> Broker
```

### Key Senior-Level Architectural Invariants:
1. **Core Basket-Trading Invariant**:
   $$\text{User Order Quantity} = \text{Folio Base Quantity} \times \text{User-Specific Multiplier}$$
2. **Explicit Position Ledger (`Position` model)**:
   - When a user subscribes, 12 explicit `Position` records are created (`quantity = base_quantity * multiplier`).
   - During rebalancing, the worker marks the outgoing stock position as `LIQUIDATED` and creates an `ACTIVE` position for the incoming stock.
   - When a user exits, the system liquidates their actual held `Position` records, ensuring 100% position accuracy even across multiple historical rebalances or mid-flight operations.
3. **Atomic Concurrency Lock (`UPDATE folios SET is_rebalancing = 1 ... WHERE is_rebalancing = 0`)**:
   - Rebalancing acquires an atomic database row conditional lock. Competing concurrent rebalance requests for the same Folio receive `409 Conflict` at the database level.
4. **Active Subscription Uniqueness (`uq_active_user_folio`)**:
   - A database partial unique index on `subscriptions(user_id, folio_id) WHERE active = 1` prevents race conditions where concurrent requests could create duplicate active subscriptions for the same user.
5. **RebalanceJob Batch Orchestration (`RebalanceJob` entity)**:
   - Rebalancing operations create a parent `RebalanceJob` record. Child tasks are linked via `job_id`, providing clean batch lifecycle tracking (`PENDING` $\rightarrow$ `PROCESSING` $\rightarrow$ `COMPLETED` / `PARTIAL_FAILURE`).
6. **Durable In-Process Background Worker**:
   - Background tasks are persisted in the database with atomic row-level claim queries (`UPDATE rebalance_tasks SET status = 'PROCESSING' WHERE id = :id AND status = 'PENDING'`).
   - **Crash Recovery**: Automatically resets stuck `PROCESSING` tasks to `PENDING` on startup, guaranteeing zero task loss across restarts.
   - **Broker Idempotency**: Trade execution keys (`rebal-{task_id}-{ticker}-{action}`) are uniquely indexed in the database to guarantee at-least-once recovery without duplicate fills.

### Persistence Strategy (SQLite vs. PostgreSQL)
- **Prototype Default**: SQLite with WAL (`PRAGMA journal_mode=WAL`) and `PRAGMA busy_timeout=30000` for zero-configuration local evaluation.
- **Production Architecture**: The data layer is decoupled via SQLAlchemy 2.0 ORM models and is directly compatible with PostgreSQL (`postgresql://...`) for multi-replica deployments with PostgreSQL row-level locks (`SELECT ... FOR UPDATE`) and Celery/Arq worker queues.

---

## 3. API Surface

### Folios
- `GET /api/folios` — List all 7 pre-seeded Folios with their 12-stock composition.
- `GET /api/folios/{folio_id}` — Get detailed stock breakdown for a specific Folio (supports integer `1` or string `'folio-1'`).

### Subscriptions
- `POST /api/subscriptions` — Subscribe a user to a Folio with multiplier (creates 12 BUY orders and 12 Position records atomically).
  - **Body**:
    ```json
    {
      "user_id": "user-101",
      "folio_id": 1,
      "multiplier": 3
    }
    ```
- `GET /api/users/{user_id}/subscriptions` — List all active and past subscriptions for a user.
- `POST /api/subscriptions/{subscription_id}/exit` — Exit a Folio, deactivating the subscription and liquidating all held positions.

### Orders / Execution Receipts
- `GET /api/orders` — View execution receipts audit log (supports `user_id`, `limit`, and `offset` query parameters).

### Admin Operations
- `POST /api/admin/rebalance` — Trigger atomic stock swap in a Folio with durable background fan-out cascade.
  - **Body**:
    ```json
    {
      "folio_id": 1,
      "outgoing_ticker": "RELIANCE",
      "incoming_ticker": "IDEA",
      "new_base_quantity": 2.0
    }
    ```
- `GET /api/admin/queue` — Real-time telemetry on background rebalance jobs and task queues.

---

## 4. Run Automated Tests

The test suite contains **31 comprehensive automated tests** covering subscriptions, exits, rebalancing cascades, multithreaded subscription races, atomic rebalance locking, crash recovery, and position ledgers:

```bash
python -m pytest -v
```

