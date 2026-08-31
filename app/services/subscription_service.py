import datetime
from typing import List, Tuple
from sqlalchemy import text
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from app.models.subscription import Subscription
from app.models.folio import Folio
from app.models.order import Order
from app.models.position import Position
from app.services.broker_service import BrokerService

class SubscriptionService:
    @staticmethod
    def get_user_subscriptions(db: Session, user_id: str) -> List[Subscription]:
        return db.query(Subscription).filter(Subscription.user_id == user_id.strip()).all()

    @staticmethod
    def get_subscription_by_id(db: Session, sub_id: int) -> Subscription:
        return db.query(Subscription).filter(Subscription.id == sub_id).first()

    @staticmethod
    def subscribe(db: Session, user_id: str, folio_id: int, multiplier: float) -> Tuple[Subscription, List[Order]]:
        cleaned_user_id = user_id.strip() if user_id else ""
        if not cleaned_user_id:
            raise ValueError("User ID is required and cannot be empty")

        if multiplier <= 0:
            raise ValueError("Multiplier must be a positive number")

        folio = db.query(Folio).filter(Folio.id == folio_id).first()
        if not folio:
            raise ValueError(f"Folio with ID {folio_id} not found")

        if len(folio.stocks) != 12:
            raise ValueError(f"Folio must contain exactly 12 stocks, but has {len(folio.stocks)}")

        # Fast read check
        existing = db.query(Subscription).filter(
            Subscription.user_id == cleaned_user_id,
            Subscription.folio_id == folio_id,
            Subscription.active == True
        ).first()
        if existing:
            raise ValueError(f"User is already active in Folio '{folio.name}'")

        # Create active subscription
        sub = Subscription(
            user_id=cleaned_user_id,
            folio_id=folio_id,
            multiplier=multiplier,
            active=True,
            status="ACTIVE"
        )
        db.add(sub)
        
        try:
            db.flush()  # to get sub.id and trigger DB unique partial index check
        except IntegrityError:
            db.rollback()
            raise ValueError(f"User is already active in Folio '{folio.name}'")

        try:
            orders = []
            now_utc = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
            
            for stock in folio.stocks:
                qty = stock.base_quantity * multiplier
                idemp_key = f"sub-{sub.id}-{stock.ticker}-BUY"
                
                # Call broker with active DB session
                receipt = BrokerService.execute_trade(
                    user_id=cleaned_user_id,
                    ticker=stock.ticker,
                    action="BUY",
                    quantity=qty,
                    idempotency_key=idemp_key,
                    db=db
                )
                
                # Persist receipt
                order = Order(
                    order_id=receipt["order_id"],
                    user_id=cleaned_user_id,
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

                # Persist explicit user Position ledger
                pos = Position(
                    subscription_id=sub.id,
                    user_id=cleaned_user_id,
                    ticker=stock.ticker,
                    quantity=qty,
                    status="ACTIVE",
                    updated_at=now_utc
                )
                db.add(pos)

            db.commit()
            db.refresh(sub)
            return sub, orders
        except Exception as e:
            db.rollback()
            raise e

    @staticmethod
    def exit_subscription(db: Session, subscription_id: int) -> Tuple[Subscription, List[Order]]:
        # Fast read check
        sub_check = db.query(Subscription).filter(Subscription.id == subscription_id).first()
        if not sub_check:
            raise ValueError(f"Subscription with ID {subscription_id} not found")
        if not sub_check.active:
            raise ValueError("Subscription is already inactive")

        # Atomic conditional update to transition active -> inactive
        exit_sql = text(
            "UPDATE subscriptions SET active = 0, status = 'EXITED' WHERE id = :id AND active = 1 AND status IN ('ACTIVE', 'REBALANCING')"
        )
        result = db.execute(exit_sql, {"id": subscription_id})
        db.flush()

        if result.rowcount == 0:
            raise ValueError("Subscription is already inactive")

        sub = db.query(Subscription).filter(Subscription.id == subscription_id).first()
        folio = db.query(Folio).filter(Folio.id == sub.folio_id).first()
        if not folio:
            raise ValueError(f"Folio with ID {sub.folio_id} not found for subscription")

        try:
            orders = []
            now_utc = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)

            # Query actual held active positions for this user subscription
            active_positions = db.query(Position).filter(
                Position.subscription_id == sub.id,
                Position.status == "ACTIVE"
            ).all()

            if active_positions:
                # Liquidate the user's explicit held positions
                for pos in active_positions:
                    idemp_key = f"exit-{sub.id}-{pos.ticker}-SELL"
                    receipt = BrokerService.execute_trade(
                        user_id=sub.user_id,
                        ticker=pos.ticker,
                        action="SELL",
                        quantity=pos.quantity,
                        idempotency_key=idemp_key,
                        db=db
                    )
                    order = Order(
                        order_id=receipt["order_id"],
                        user_id=sub.user_id,
                        subscription_id=sub.id,
                        ticker=pos.ticker,
                        action="SELL",
                        quantity=pos.quantity,
                        status=receipt["status"],
                        idempotency_key=idemp_key,
                        timestamp=receipt["timestamp"]
                    )
                    db.add(order)
                    orders.append(order)
                    pos.status = "LIQUIDATED"
                    pos.updated_at = now_utc
            else:
                # Fallback for legacy subscriptions
                for stock in folio.stocks:
                    qty = stock.base_quantity * sub.multiplier
                    idemp_key = f"exit-{sub.id}-{stock.ticker}-SELL"
                    receipt = BrokerService.execute_trade(
                        user_id=sub.user_id,
                        ticker=stock.ticker,
                        action="SELL",
                        quantity=qty,
                        idempotency_key=idemp_key,
                        db=db
                    )
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
