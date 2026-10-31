"""Application review, allocation lifecycle and handover verification.

State machine implemented here:

    application: submitted -> approved | rejected
    allocation : offered -> accepted -> handover_confirmed -> completed
                              └────────────────> expired | cancelled

Payment eligibility requires `handover_confirmed`. The payment service
re-verifies the same conditions independently (defence in depth).
"""
from datetime import datetime, timedelta, timezone

from ..constants import (
    AllocationStatus,
    ApplicationStatus,
    HandoverRole,
    NotificationType,
    StandStatus,
    zones_for_category,
)
from ..errors import ApiError
from ..extensions import db
from ..models import (
    Allocation,
    Application,
    HandoverConfirmation,
    Stand,
    User,
    Vendor,
)
from .audit_service import AuditService
from .notification_service import NotificationService
from .payment_conditions import PaymentConditions
from .moment import as_utc

OFFER_VALIDITY_HOURS = 48


class AllocationService:
    # ------------------------------------------------------------------ queue
    @staticmethod
    def next_queue_position() -> int:
        from sqlalchemy import func

        return (db.session.query(func.max(Application.queue_position)).scalar() or 0) + 1

    # ------------------------------------------------------- application flow
    @staticmethod
    def create_application(vendor: Vendor, payload: dict, actor: str, actor_role: str) -> Application:
        active = (
            db.session.query(Application)
            .filter(
                Application.vendor_id == vendor.id,
                Application.status.in_(
                    [
                        ApplicationStatus.SUBMITTED,
                        ApplicationStatus.UNDER_REVIEW,
                        ApplicationStatus.APPROVED,
                    ]
                ),
            )
            .first()
        )
        if active is not None:
            raise ApiError(
                409,
                "application_exists",
                "You already have an application in the queue.",
                {"application_id": active.id, "status": active.status},
            )

        application = Application(
            vendor_id=vendor.id,
            business_type=payload["business_type"],
            preferred_zone=payload.get("preferred_zone"),
            notes=payload.get("notes"),
            status=ApplicationStatus.SUBMITTED,
            queue_position=AllocationService.next_queue_position(),
        )
        db.session.add(application)
        NotificationService.push(
            vendor.user_id,
            NotificationType.APPLICATION_RECEIVED,
            "Application received",
            "Your stand application has been received and is waiting for council review.",
            {"application_id": application.id, "queue_position": application.queue_position},
        )
        AuditService.record(
            "APPLICATION_SUBMITTED",
            actor=actor,
            actor_role=actor_role,
            entity_type="application",
            entity_id=application.id,
            details=f"Vendor {vendor.full_name} ({vendor.nrc}) applied for a stand.",
        )
        return application

    @staticmethod
    def review_application(
        application: Application, decision: str, reviewer: User, reason: str | None = None
    ) -> Application:
        if application.status not in (ApplicationStatus.SUBMITTED, ApplicationStatus.UNDER_REVIEW):
            raise ApiError(409, "invalid_state", f"Application is already {application.status}.")

        if decision == "approved":
            application.status = ApplicationStatus.APPROVED
            NotificationService.push(
                application.vendor.user_id,
                NotificationType.APPLICATION_APPROVED,
                "Application approved",
                "Your application was approved. A council official will offer you an available stand.",
                {"application_id": application.id},
            )
            AuditService.record(
                "APPLICATION_APPROVED",
                actor=reviewer.id,
                actor_role=reviewer.role,
                entity_type="application",
                entity_id=application.id,
                details=f"Approved by {reviewer.full_name}.",
            )
        elif decision == "rejected":
            application.status = ApplicationStatus.REJECTED
            application.decision_reason = (reason or "Not specified.")[:255]
            NotificationService.push(
                application.vendor.user_id,
                NotificationType.APPLICATION_REJECTED,
                "Application rejected",
                f"Your application was rejected: {application.decision_reason}",
                {"application_id": application.id, "reason": application.decision_reason},
            )
            AuditService.record(
                "APPLICATION_REJECTED",
                actor=reviewer.id,
                actor_role=reviewer.role,
                entity_type="application",
                entity_id=application.id,
                details=f"Rejected by {reviewer.full_name}: {application.decision_reason}",
            )
        else:
            raise ApiError(400, "invalid_decision", "decision must be 'approved' or 'rejected'.")

        application.reviewed_by = reviewer.id
        application.reviewed_at = datetime.now(timezone.utc)
        return application

    # ------------------------------------------------------------ allocations
    @staticmethod
    def assign_stand(application: Application, admin: User) -> Allocation:
        """Pick the best available stand for an approved application.

        Scoring mirrors the existing frontend matcher: +10 when the zone suits
        the vendor's business category, +20 when it matches the preferred zone.
        """
        if application.status != ApplicationStatus.APPROVED:
            raise ApiError(409, "application_not_approved", "Approve the application before assigning a stand.")

        vendor = application.vendor
        suited = zones_for_category(vendor.business_type)
        candidates = (
            db.session.query(Stand)
            .filter(Stand.status == StandStatus.AVAILABLE)
            .order_by(Stand.code)
            .all()
        )
        if not candidates:
            raise ApiError(409, "no_stands_available", "No stands are available right now.")

        def score(stand: Stand) -> int:
            return (10 if stand.zone in suited else 0) + (20 if stand.zone == vendor.preferred_zone else 0)

        stand = max(candidates, key=lambda s: (score(s), s.code))
        return AllocationService.create_allocation(application, stand, admin)

    @staticmethod
    def create_allocation(application: Application, stand: Stand, admin: User) -> Allocation:
        if application.status != ApplicationStatus.APPROVED:
            raise ApiError(409, "application_not_approved", "Approve the application before offering a stand.")
        if stand.status != StandStatus.AVAILABLE:
            raise ApiError(409, "stand_unavailable", f"Stand {stand.code} is {stand.status}.")

        now = datetime.now(timezone.utc)
        allocation = Allocation(
            application_id=application.id,
            stand_id=stand.id,
            vendor_id=application.vendor_id,
            status=AllocationStatus.OFFERED,
            offered_by=admin.id,
            offered_at=now,
            offer_expires_at=now + timedelta(hours=OFFER_VALIDITY_HOURS),
            fee_amount=stand.fee_amount,
            currency=stand.currency,
        )
        stand.status = StandStatus.RESERVED
        stand.hold_expires_at = allocation.offer_expires_at
        application.status = ApplicationStatus.ALLOCATED
        db.session.add(allocation)
        NotificationService.push(
            application.vendor.user_id,
            NotificationType.ALLOCATION_OFFERED,
            "Stand offer waiting",
            f"Stand {stand.code} in {stand.zone} was offered to you. Accept it to continue.",
            {"allocation_id": allocation.id, "stand_code": stand.code},
        )
        AuditService.record(
            "ALLOCATION_OFFERED",
            actor=admin.id,
            actor_role=admin.role,
            entity_type="allocation",
            entity_id=allocation.id,
            details=f"Stand {stand.code} offered for application {application.id}.",
        )
        return allocation

    @staticmethod
    def accept_allocation(allocation: Allocation, vendor_user: User) -> Allocation:
        if allocation.status != AllocationStatus.OFFERED:
            raise ApiError(409, "invalid_state", f"Allocation is {allocation.status}; only offered allocations can be accepted.")
        if allocation.offer_expires_at and as_utc(allocation.offer_expires_at) < datetime.now(timezone.utc):
            allocation.status = AllocationStatus.EXPIRED
            allocation.stand.status = StandStatus.AVAILABLE
            allocation.stand.hold_expires_at = None
            raise ApiError(410, "offer_expired", "The stand offer expired. Ask the council for a new offer.")

        allocation.status = AllocationStatus.ACCEPTED
        allocation.accepted_at = datetime.now(timezone.utc)
        NotificationService.push(
            vendor_user.id,
            NotificationType.ALLOCATION_ACCEPTED,
            "Stand accepted",
            f"You accepted stand {allocation.stand.code}. Meet a council official for handover verification.",
            {"allocation_id": allocation.id},
        )
        AuditService.record(
            "ALLOCATION_ACCEPTED",
            actor=vendor_user.id,
            actor_role=vendor_user.role,
            entity_type="allocation",
            entity_id=allocation.id,
            details=f"Vendor accepted stand {allocation.stand.code}.",
        )
        return allocation

    @staticmethod
    def cancel_allocation(allocation: Allocation, admin: User, reason: str) -> Allocation:
        if allocation.status == AllocationStatus.COMPLETED:
            raise ApiError(409, "invalid_state", "Completed allocations cannot be cancelled.")
        allocation.status = AllocationStatus.CANCELLED
        allocation.cancelled_reason = reason[:255]
        if allocation.stand.status in (StandStatus.RESERVED,):
            allocation.stand.status = StandStatus.AVAILABLE
            allocation.stand.hold_expires_at = None
        AuditService.record(
            "ALLOCATION_CANCELLED",
            actor=admin.id,
            actor_role=admin.role,
            entity_type="allocation",
            entity_id=allocation.id,
            details=f"Cancelled: {reason}",
        )
        return allocation

    # --------------------------------------------------------------- handover
    @staticmethod
    def confirm_handover(
        allocation: Allocation,
        role: HandoverRole,
        confirmer: User,
        meeting_location: str | None = None,
        notes: str | None = None,
    ) -> Allocation:
        if allocation.status != AllocationStatus.ACCEPTED:
            raise ApiError(409, "invalid_state", f"Allocation is {allocation.status}; handover needs an accepted allocation.")

    @staticmethod
    def confirmation_roles(allocation_id: str) -> set[str]:
        """Roles already confirmed, read straight from the table.

        (Relying on the cached `confirmations` collection after a same-session
        insert misses the new row, so we query instead.)
        """
        rows = db.session.query(HandoverConfirmation.role).filter_by(allocation_id=allocation_id)
        return {row[0] for row in rows}

    @staticmethod
    def confirm_handover(
        allocation: Allocation,
        role: HandoverRole,
        confirmer: User,
        meeting_location: str | None = None,
        notes: str | None = None,
    ) -> Allocation:
        if allocation.status != AllocationStatus.ACCEPTED:
            raise ApiError(409, "invalid_state", f"Allocation is {allocation.status}; handover needs an accepted allocation.")

        roles_present = AllocationService.confirmation_roles(allocation.id)
        if role.value in roles_present:
            raise ApiError(409, "already_confirmed", f"Handover already confirmed by the {role.value}.")

        db.session.add(
            HandoverConfirmation(
                allocation_id=allocation.id,
                role=role.value,
                confirmed_by=confirmer.id,
                confirmed_at=datetime.now(timezone.utc),
                meeting_location=meeting_location,
                notes=notes,
            )
        )
        roles_present.add(role.value)

        both_present = {
            HandoverRole.VENDOR.value,
            HandoverRole.OFFICIAL.value,
        } <= roles_present
        if both_present:
            allocation.status = AllocationStatus.HANDOVER_CONFIRMED
            NotificationService.push(
                allocation.vendor.user_id,
                NotificationType.HANDOVER_CONFIRMED,
                "Handover verified",
                "Both parties confirmed the handover. You may now settle the stand levy.",
                {"allocation_id": allocation.id},
            )

        AuditService.record(
            "HANDOVER_CONFIRMED" if both_present else "HANDOVER_PARTIAL",
            actor=confirmer.id,
            actor_role=confirmer.role,
            entity_type="allocation",
            entity_id=allocation.id,
            details=f"Handover confirmed by {role.value}.",
        )
        return allocation

    # ------------------------------------------------------------ eligibility
    @staticmethod
    def eligibility(allocation: Allocation) -> dict:
        """Why (not) can this allocation be paid for right now?"""
        reasons: list[str] = []

        if allocation.status == AllocationStatus.COMPLETED:
            reasons.append("Allocation already completed — a permit exists.")
        elif allocation.status != AllocationStatus.HANDOVER_CONFIRMED:
            reasons.append("Handover not yet confirmed by both the vendor and the council official.")

        roles_present = AllocationService.confirmation_roles(allocation.id)
        if HandoverRole.VENDOR.value not in roles_present:
            reasons.append("Vendor handover confirmation missing.")
        if HandoverRole.OFFICIAL.value not in roles_present:
            reasons.append("Council official handover confirmation missing.")

        reasons += PaymentConditions.blocked_by(
            allocation.id, allocation.fee_amount, allocation.currency
        )
        return {"eligible": not reasons, "reasons": reasons}
