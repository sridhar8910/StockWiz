import uuid
import datetime
from typing import Optional, Dict
from app.db.database import SessionLocal
from app.models.order import Order

class BrokerService:
    # In-memory fallback cache
    _executed_receipts: Dict[str, dict] = {}

    @classmethod
    def reset_cache(cls) -> None:
        """Helper to clear broker cache in test suites."""
        cls._executed_receipts.clear()

    @classmethod
    def execute_trade(
        cls,
        user_id: str,
        ticker: str,
        action: str,
        quantity: float,
        idempotency_key: Optional[str] = None
    ) -> dict:
        if not user_id or not user_id.strip():
            raise ValueError("user_id is required and cannot be empty")
        if not ticker or not ticker.strip():
            raise ValueError("ticker is required and cannot be empty")
        
        normalized_action = action.strip().upper()
        if normalized_action not in ("BUY", "SELL"):
            raise ValueError("action must be BUY or SELL")
        if quantity <= 0:
            raise ValueError("quantity must be greater than zero")

        # 1. Durable Idempotency: Check database first if key exists
        if idempotency_key:
            db = SessionLocal()
            try:
                existing_order = db.query(Order).filter(Order.idempotency_key == idempotency_key).first()
                if existing_order:
                    return {
                        "order_id": existing_order.order_id,
                        "status": existing_order.status,
                        "timestamp": existing_order.timestamp,
                        "user_id": existing_order.user_id,
                        "ticker": existing_order.ticker,
                        "action": existing_order.action,
                        "quantity": float(existing_order.quantity),
                        "idempotency_key": existing_order.idempotency_key
                    }
            except Exception:
                pass
            finally:
                db.close()

            # 2. Check in-memory ledger
            if idempotency_key in cls._executed_receipts:
                return cls._executed_receipts[idempotency_key]

        order_id = f"ord-{uuid.uuid4().hex[:12]}"
        now_utc = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
        
        receipt = {
            "order_id": order_id,
            "status": "EXECUTED",
            "timestamp": now_utc,
            "user_id": user_id.strip(),
            "ticker": ticker.strip().upper(),
            "action": normalized_action,
            "quantity": float(quantity),
            "idempotency_key": idempotency_key
        }

        if idempotency_key:
            cls._executed_receipts[idempotency_key] = receipt

        return receipt
