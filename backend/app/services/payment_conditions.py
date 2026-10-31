"""Single source of truth for the money-safety rules.

Both the allocation eligibility endpoint and the payment service read from
here, so a rule can never drift between "can pay" and "will pay".
"""
from decimal import Decimal

from flask import current_app

from ..extensions import db
from ..models import Payment


class PaymentConditions:
    OPEN_STATUSES = ("pending", "successful")

    @staticmethod
    def team_spend_total(currency: str) -> Decimal:
        """Sum of pending + successful DevDraft payments (refunds excluded)."""
        rows = (
            db.session.query(Payment.amount)
            .filter(Payment.status.in_(PaymentConditions.OPEN_STATUSES))
            .filter(Payment.currency == currency)
            .all()
        )
        return sum((row[0] for row in rows), Decimal("0"))

    @staticmethod
    def blocked_by(allocation_id: str, amount: Decimal, currency: str) -> list[str]:
        """Reasons this allocation payment must not proceed (may be empty)."""
        app = current_app._get_current_object()
        reasons: list[str] = []

        existing = (
            db.session.query(Payment)
            .filter(Payment.allocation_id == allocation_id)
            .filter(Payment.status.in_(PaymentConditions.OPEN_STATUSES))
            .first()
        )
        if existing is not None:
            reasons.append(f"A payment for this allocation already exists (status: {existing.status}).")

        max_tx: Decimal = app.config["PAYMENT_MAX_PER_TRANSACTION"]
        if amount > max_tx:
            reasons.append(f"Per-transaction limit is {max_tx} {currency} (requested {amount}).")

        max_total: Decimal = app.config["PAYMENT_MAX_TEAM_TOTAL"]
        spent = PaymentConditions.team_spend_total(currency)
        if spent + amount > max_total:
            reasons.append(
                f"Team volume limit is {max_total} {currency}; {spent} already committed, "
                f"{amount} more would exceed it."
            )
        return reasons
