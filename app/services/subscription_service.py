from typing import List, Tuple
from sqlalchemy.orm import Session
from app.models.subscription import Subscription
from app.models.folio import Folio
from app.models.order import Order
from app.services.broker_service import BrokerService

class SubscriptionService:
    @staticmethod
    def get_user_subscriptions(db: Session, user_id: str) -> List[Subscription]:
        return db.query(Subscription).filter(Subscription.user_id == user_id).all()

    @staticmethod
    def get_subscription_by_id(db: Session, sub_id: int) -> Subscription:
        return db.query(Subscription).filter(Subscription.id == sub_id).first()

    @staticmethod
    def subscribe(db: Session, user_id: str, folio_id: int, multiplier: float) -> Tuple[Subscription, List[Order]]:
        if not user_id or not user_id.strip():
            raise ValueError("User ID is required and cannot be empty")

        if multiplier <= 0:
            raise ValueError("Multiplier must be a positive number")

        folio = db.query(Folio).filter(Folio.id == folio_id).first()
        if not folio:
            raise ValueError(f"Folio with ID {folio_id} not found")

        if len(folio.stocks) != 12:
            raise ValueError(f"Folio must contain exactly 12 stocks, but has {len(folio.stocks)}")

        # Check if already active
        existing = db.query(Subscription).filter(
            Subscription.user_id == user_id,
            Subscription.folio_id == folio_id,
            Subscription.active == True
        ).first()
        if existing:
            raise ValueError(f"User is already active in Folio '{folio.name}'")

        # Create active subscription
        sub = Subscription(
            user_id=user_id,
            folio_id=folio_id,
            multiplier=multiplier,
            active=True
        )
        db.add(sub)
        
        try:
            db.flush()  # to get sub.id
            orders = []
            for stock in folio.stocks:
                qty = stock.base_quantity * multiplier
                idemp_key = f"sub-{sub.id}-{stock.ticker}-BUY"
                # Call broker
                receipt = BrokerService.execute_trade(
                    user_id=user_id,
                    ticker=stock.ticker,
                    action="BUY",
                    quantity=qty,
                    idempotency_key=idemp_key
                )
                # Persist receipt
                order = Order(
                    order_id=receipt["order_id"],
                    user_id=user_id,
                    subscription_id=sub.id,
                    ticker=stock.ticker,
                    action="BUY",
                    quantity=qty,
                    status=receipt["status"],
                    idempotency_key=idemp_key,
                    timestamp=receipt["timestamp"]
                )
                db.add(order)
                orders.append(order)

            db.commit()
            db.refresh(sub)
            return sub, orders
        except Exception as e:
            db.rollback()
            raise e

    @staticmethod
    def exit_subscription(db: Session, subscription_id: int) -> Tuple[Subscription, List[Order]]:
        sub = db.query(Subscription).filter(Subscription.id == subscription_id).first()
        if not sub:
            raise ValueError(f"Subscription with ID {subscription_id} not found")
        
        if not sub.active:
            raise ValueError("Subscription is already inactive")

        folio = db.query(Folio).filter(Folio.id == sub.folio_id).first()
        if not folio:
            raise ValueError(f"Folio with ID {sub.folio_id} not found for subscription")

        try:
            # Mark subscription as inactive inside transaction
            sub.active = False
            db.flush()
            orders = []
            for stock in folio.stocks:
                qty = stock.base_quantity * sub.multiplier
                idemp_key = f"exit-{sub.id}-{stock.ticker}-SELL"
                # Call broker
                receipt = BrokerService.execute_trade(
                    user_id=sub.user_id,
                    ticker=stock.ticker,
                    action="SELL",
                    quantity=qty,
                    idempotency_key=idemp_key
                )
                # Persist receipt
                order = Order(
                    order_id=receipt["order_id"],
                    user_id=sub.user_id,
                    subscription_id=sub.id,
                    ticker=stock.ticker,
                    action="SELL",
                    quantity=qty,
                    status=receipt["status"],
                    idempotency_key=idemp_key,
                    timestamp=receipt["timestamp"]
                )
                db.add(order)
                orders.append(order)

            db.commit()
            db.refresh(sub)
            return sub, orders
        except Exception as e:
            db.rollback()
            raise e
