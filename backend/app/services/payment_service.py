"""Programmable payment workflow.

Deliberately strict rules (docs/PAYMENT_FLOW.md):
  * Payment initiation only after `handover_confirmed` (vendor + official).
  * Backend re-computes every condition; the frontend cannot "click through".
  * Provider result is verified server-side (GET status + signed webhooks);
    button clicks and redirects never mark money as received.
  * Idempotency-Key is required (matching DevDraft) and persisted locally.
  * Amounts come from DB records (stand fee), never from the request body.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from decimal import Decimal

from flask import current_app, request

from ..constants import AllocationStatus, HandoverRole, NotificationType, StandStatus
from ..errors import ApiError
from ..extensions import db
from ..models import (
    Allocation,
    Payment,
    PaymentEvent,
    User,
    Vendor,
    permit_code,
)
from .audit_service import AuditService
from .devdraft import DevDraftError, get_provider, normalize_status
from .notification_service import NotificationService


class PaymentService:
    # ------------------------------------------------------------- initiation
    @staticmethod
    def initiate(allocation: Allocation, actor: User, idempotency_key: str | None = None) -> Payment:
        app = current_app._get_current_object()
        key = (idempotency_key or request.headers.get("Idempotency-Key", "")).strip()
        if not key:
            raise ApiError(400, "idempotency_key_required",
                           "An Idempotency-Key header (UUID) is required to start a payment.")
        if len(key) < 6 or len(key) > 64 or not key.replace("-", "").replace("_", "").isalnum():
            raise ApiError(400, "idempotency_key_invalid",
                           "Idempotency-Key must be 6-64 alphanumeric characters (dashes/underscores allowed).")

        # Idempotent replay: same key -> same payment, no duplicate charge.
        existing = db.session.query(Payment).filter_by(idempotency_key=key).first()
        if existing is not None:
            if existing.allocation_id != allocation.id:
                raise ApiError(409, "idempotency_conflict",
                               "This Idempotency-Key belongs to a different payment.")
            return existing

        from .allocation_service import AllocationService

        verdict = AllocationService.eligibility(allocation)
        if not verdict["eligible"]:
            raise ApiError(409, "payment_not_eligible",
                           "This allocation cannot be paid yet.", {"reasons": verdict["reasons"]})

        vendor: Vendor = allocation.vendor
        amount = allocation.fee_amount
        currency = (allocation.currency or app.config["PAYMENT_CURRENCY"]).upper()

        payment = Payment(
            allocation_id=allocation.id,
            vendor_id=vendor.id,
            amount=amount,
            currency=currency,
            status="pending",
            provider=f"devdraft-{app.config['DEVDRAFT_MODE']}",
            idempotency_key=key,
            description=f"PaMarket stand levy {allocation.stand.code} ({vendor.nrc})",
        )
        db.session.add(payment)
        db.session.flush()  # assign payment.id before provider call

        PaymentService.record_provider_call(payment, "payment_created_request", {"amount": str(amount), "currency": currency})

        try:
            provider = get_provider()
            result = provider.create_payment(
                amount=amount,
                currency=currency,
                description=payment.description,
                idempotency_key=key,
                customer_reference=vendor.nrc.replace("/", ""),
            )
        except DevDraftError as exc:
            payment.status = "failed"
            payment.provider_status_raw = str(exc.code)
            PaymentService._record_event(payment, "provider_creation_error", raw_status=exc.code, signature_valid=None,
                                         payload={"message": str(exc)})
            NotificationService.push(
                vendor.user_id, NotificationType.PAYMENT_FAILED, "Payment request failed",
                "The payment could not be started. No money moved — please try again.",
                {"payment_id": payment.id},
            )
            AuditService.record(
                "PAYMENT_REQUEST_FAILED", actor=actor.id, actor_role=actor.role,
                entity_type="payment", entity_id=payment.id, details=str(exc.message),
            )
            db.session.commit()
            raise ApiError(exc.status if exc.status >= 400 else 502, exc.code,
                           "The payment provider rejected the request. No money moved.")

        payment.provider_reference = result["provider_reference"]
        payment.provider_status_raw = result["provider_status_raw"]
        payment.status = normalize_status(result["provider_status_raw"])
        PaymentService._record_event(
            payment, "provider_creation_response",
            raw_status=result["provider_status_raw"], signature_valid=None, payload=result["raw"],
        )

        if payment.status == "successful":
            PaymentService._mark_successful(payment, actor)
        elif payment.status == "failed":
            NotificationService.push(
                vendor.user_id, NotificationType.PAYMENT_FAILED, "Payment failed",
                "The payment did not succeed. No money moved — please try again.",
                {"payment_id": payment.id},
            )

        db.session.commit()
        return payment

    @staticmethod
    def _record_event(payment: Payment, event_type: str, *, raw_status: str | None,
                      signature_valid: bool | None, payload: dict | None,
                      provider_event_id: str | None = None) -> PaymentEvent:
        event = PaymentEvent(
            payment_id=payment.id,
            event_type=event_type,
            raw_status=raw_status,
            signature_valid=signature_valid,
            payload=payload,
            provider_event_id=provider_event_id,
        )
        db.session.add(event)
        return event

    @staticmethod
    def record_provider_call(payment: Payment, event_type: str, payload: dict) -> PaymentEvent:
        event = PaymentEvent(
            payment_id=payment.id,
            event_type=event_type,
            payload=payload,
        )
        db.session.add(event)
        return event

    # --------------------------------------------------------------- success
    @staticmethod
    def _mark_successful(payment: Payment, actor: User | None = None) -> None:
        if payment.status == "successful" and payment.receipt_no:
            return  # already terminal — repeated webhooks are no-ops
        allocation: Allocation = payment.allocation
        if allocation.status == AllocationStatus.COMPLETED:
            return

        payment.completed_at = datetime.now(timezone.utc)

        PaymentService._issue_receipt_and_permit(payment, allocation)

        if actor is not None:
            AuditService.record(
                "PAYMENT_VERIFIED_SUCCESSFUL",
                actor=actor.id,
                actor_role=actor.role,
                entity_type="payment",
                entity_id=payment.id,
                details=f"Verified via provider; receipt {payment.receipt_no}.",
            )
        else:
            AuditService.record(
                "PAYMENT_VERIFIED_SUCCESSFUL",
                actor="webhook:devdraft",
                actor_role="system",
                entity_type="payment",
                entity_id=payment.id,
                details=f"Verified via signed webhook; receipt {payment.receipt_no}.",
            )

    @staticmethod
    def _issue_receipt_and_permit(payment: Payment, allocation: Allocation) -> None:
        app = current_app._get_current_object()
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d")
        payment.receipt_no = f"PAM-{stamp}-{uuid.uuid4().hex[:8].upper()}"

        payment.receipt_issued_at = datetime.now(timezone.utc)
        allocation.status = AllocationStatus.COMPLETED
        allocation.completed_at = payment.completed_at
        allocation.permit_code = permit_code()

        stand = allocation.stand
        stand.status = StandStatus.OCCUPIED
        stand.allocated_at = payment.completed_at
        stand.hold_expires_at = None
        stand.vendor_id = allocation.vendor_id
        stand.vendor_name = allocation.vendor.full_name
        stand.vendor_nrc = allocation.vendor.nrc

        vendor_user = allocation.vendor.user
        NotificationService.push(
            vendor_user.id,
            NotificationType.PAYMENT_SUCCESSFUL,
            "Payment received — permit ready",
            f"Payment {payment.receipt_no} was verified. Permit {allocation.permit_code} "
            f"is active for stand {stand.code}.",
            {"payment_id": payment.id, "permit_code": allocation.permit_code},
        )

    # ------------------------------------------------------------ status sync
    @staticmethod
    def sync(payment: Payment, actor: User | None = None) -> Payment:
        """Explicit server-side verification against the provider."""
        if not payment.provider_reference:
            raise ApiError(409, "no_provider_reference", "This payment has no provider reference yet.")
        try:
            result = get_provider().get_payment(payment.provider_reference)
        except DevDraftError as exc:
            PaymentService._record_event(payment, "status_check_error", raw_status=exc.code,
                                         signature_valid=None, payload={"message": str(exc)})
            db.session.commit()
            raise ApiError(502, "provider_unavailable",
                           "Could not verify payment with DevDraft right now. Try again shortly.")

        new_status = normalize_status(result["status_raw"])
        changed = new_status != payment.status
        payment.provider_status_raw = result["status_raw"]
        if new_status != payment.status:
            payment.status = new_status

        PaymentService._record_event(
            payment, "status_sync", raw_status=result["status_raw"], signature_valid=None, payload=result["raw"]
        )

        if payment.status == "successful":
            PaymentService._mark_successful(payment, actor)
        elif payment.status == "failed":
            NotificationService.push(
                payment.vendor.user_id, NotificationType.PAYMENT_FAILED, "Payment failed",
                "The payment did not succeed. No money moved — please try again.",
                {"payment_id": payment.id},
            )

        db.session.commit()
        return payment

    # -------------------------------------------------------------- webhooks
    @staticmethod
    def handle_webhook(raw_body: bytes, signature: str | None) -> dict:
        app = current_app._get_current_object()
        if app.config["DEVDRAFT_MODE"] == "sandbox" and not app.config.get("DEVDRAFT_WEBHOOK_SECRET"):
            # Sandbox without a configured secret: accept only in explicit dev mode
            signature_valid = True
        else:
            signature_valid = get_provider().verify_webhook(raw_body, signature)
        if not signature_valid:
            raise ApiError(401, "invalid_webhook_signature", "Webhook signature verification failed.")

        try:
            payload = json.loads(raw_body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise ApiError(400, "invalid_webhook_payload", "Webhook body is not valid JSON.")

        event_id = payload.get("id")
        event_type = (payload.get("type") or "").lower()
        data_object = (payload.get("data") or {}).get("object") or {}
        provider_reference = data_object.get("id")
        raw_status = data_object.get("status")

        if not event_id or not event_type:
            raise ApiError(400, "invalid_webhook_payload", "Webhook is missing id/type fields.")

        # DevDraft retries with exponential backoff (up to 5 attempts) — the same
        # event id must be processed exactly once.
        duplicate = (
            db.session.query(PaymentEvent).filter_by(provider_event_id=str(event_id)).first()
        )
        if duplicate is not None:
            return {"status": "ok", "action": "duplicate_ignored", "event_id": str(event_id)}

        payment = (
            db.session.query(Payment).filter_by(provider_reference=provider_reference).first()
            if provider_reference else None
        )

        if payment is None:
            # Store nothing financial; unknown provider object — acknowledge.
            return {"status": "ok", "action": "unmatched", "event_id": str(event_id)}

        db.session.add(
            PaymentEvent(
                payment_id=payment.id,
                event_type=f"webhook:{event_type}",
                provider_event_id=str(event_id),
                raw_status=raw_status,
                signature_valid=signature_valid,
                payload=payload,
            )
        )

        new_status = normalize_status(raw_status)
        payment.provider_status_raw = raw_status

        if payment.status in ("successful", "refunded"):
            db.session.commit()
            return {"status": "ok", "action": "already_final"}
        if new_status != "pending":
            payment.status = new_status

        if payment.status == "successful":
            PaymentService._mark_successful(payment, None)
        elif payment.status == "failed":
            NotificationService.push(
                payment.vendor.user_id, NotificationType.PAYMENT_FAILED, "Payment failed",
                "DevDraft reports the payment failed. No money moved — start a new payment.",
                {"payment_id": payment.id},
            )
        elif payment.status == "refunded":
            NotificationService.push(
                payment.vendor.user_id, NotificationType.PAYMENT_REFUNDED, "Payment refunded",
                f"Payment {payment.receipt_no or payment.provider_reference} was refunded.",
                {"payment_id": payment.id},
            )
        db.session.commit()
        return {"status": "ok", "action": "processed", "event_id": str(event_id)}

    # ---------------------------------------------------------------- refunds
    @staticmethod
    def refund(payment: Payment, actor: User, reason: str | None = None) -> Payment:
        if payment.status != "successful":
            raise ApiError(409, "invalid_state", "Only successful payments can be refunded.")
        try:
            result = get_provider().refund_payment(
                payment.provider_reference, idempotency_key=f"refund_{payment.id}_{uuid.uuid4().hex[:8]}"
            )
        except DevDraftError as exc:
            raise ApiError(exc.status if exc.status >= 400 else 502, exc.code,
                           f"Refund failed: {exc}")

        payment.status = "refunded"
        PaymentService._record_event(
            payment, "refund", raw_status=result["status_raw"], signature_valid=None, payload=result["raw"]
        )

        allocation = payment.allocation
        if allocation.status == AllocationStatus.COMPLETED:
            allocation.status = AllocationStatus.CANCELLED
            allocation.cancelled_reason = "Stand levy refunded."
            allocation.permit_code = None
            stand = allocation.stand
            stand.status = StandStatus.AVAILABLE
            stand.vendor_id = None
            stand.vendor_name = None
            stand.vendor_nrc = None
            stand.allocated_at = None

        NotificationService.push(
            payment.vendor.user_id, NotificationType.PAYMENT_REFUNDED, "Refund issued",
            f"Payment {payment.receipt_no} was refunded to the payer{': ' + reason if reason else '.'}",
            {"payment_id": payment.id},
        )
        AuditService.record(
            "PAYMENT_REFUNDED", actor=actor.id, actor_role=actor.role,
            entity_type="payment", entity_id=payment.id,
            details=f"Refunded {payment.amount} {payment.currency}. {reason or ''}",
        )
        db.session.commit()
        return payment

    # ---------------------------------------------------------------- helpers
    @staticmethod
    def receipt(payment: Payment) -> dict:
        allocation = payment.allocation
        vendor: Vendor = payment.vendor
        app = current_app._get_current_object()
        return {
            "issuer": app.config.get("APP_NAME", "PaMarket"),
            "receipt_no": payment.receipt_no,
            "payment_id": payment.id,
            "allocation_id": allocation.id,
            "permit_code": allocation.permit_code,
            "stand_code": allocation.stand.code,
            "zone": allocation.stand.zone,
            "vendor_name": vendor.full_name,
            "vendor_nrc": vendor.nrc,
            "amount": f"{payment.amount:.2f}",
            "currency": payment.currency,
            "provider": payment.provider,
            "provider_reference": payment.provider_reference,
            "status": payment.status,
            "paid_at": payment.completed_at.isoformat() if payment.completed_at else None,
            "events": [
                {
                    "id": e.id,
                    "type": e.event_type,
                    "raw_status": e.raw_status,
                    "signature_valid": e.signature_valid,
                    "at": e.created_at.isoformat(),
                }
                for e in payment.events
            ],
        }

    # ------------------------------------------------------------- serialization
    @staticmethod
    def to_dict(payment: Payment) -> dict:
        return {
            "id": payment.id,
            "allocation_id": payment.allocation_id,
            "vendor_id": payment.vendor_id,
            "amount": f"{payment.amount:.2f}",
            "currency": payment.currency,
            "status": payment.status,
            "provider": payment.provider,
            "provider_reference": payment.provider_reference,
            "receipt_no": payment.receipt_no,
            "idempotency_key": payment.idempotency_key,
            "created_at": payment.created_at.isoformat(),
            "completed_at": payment.completed_at.isoformat() if payment.completed_at else None,
        }
