"""Market stand grid: reference data, provisioned without the demo seeder.

The 8×12 stand grid is the council's market layout — it must exist on every
deployment (including production, where `flask seed-demo` is disabled and
ALLOW_DEMO_SEED is off). `ensure_market_grid` is idempotent: it only creates
the grid when the stands table is empty. Every stand starts `available`;
occupancy develops through real allocations, never seed data.

Pricing: front-row premium. Row 0 (closest to the main entrance) carries the
highest monthly fee, decreasing by $0.20 per row down to the back row
($5.00 → $3.60 for eight rows). The front fee is clamped to the deployed
per-transaction payment cap so no stand can ever be unpayable.
"""
import logging
from decimal import Decimal

log = logging.getLogger(__name__)

GRID_ROWS = 8
GRID_COLS = 12

FRONT_ROW_FEE = Decimal("5.00")
ROW_DECREMENT = Decimal("0.20")
MIN_FEE = Decimal("1.00")


def zone_for_col(col: int, market_zones: tuple[str, ...]) -> str:
    """Deterministic zoning: three adjacent columns per zone, wrapping."""
    return list(market_zones)[(col // 3) % len(market_zones)]


def fee_for_row(row: int, per_transaction_cap: Decimal | None = None) -> Decimal:
    fee = FRONT_ROW_FEE - Decimal(row) * ROW_DECREMENT
    if per_transaction_cap is not None:
        fee = min(fee, per_transaction_cap)
    return max(fee, MIN_FEE).quantize(Decimal("0.01"))


def ensure_market_grid(app) -> None:
    """Create the full stand grid once, if the deployment has no stands yet."""
    from ..constants import MARKET_ZONES
    from ..constants import StandStatus
    from ..extensions import db
    from ..models import Stand

    with app.app_context():
        try:
            existing_codes = {code for (code,) in db.session.query(Stand.code).all()}
            cap = app.config["PAYMENT_MAX_PER_TRANSACTION"]
            missing: list[Stand] = []
            index = 0
            for row in range(GRID_ROWS):
                for col in range(GRID_COLS):
                    index += 1
                    code = f"ST-{index:03d}"
                    if code not in existing_codes:
                        missing.append(
                            Stand(
                                code=code,
                                row=row,
                                col=col,
                                zone=zone_for_col(col, MARKET_ZONES),
                                status=StandStatus.AVAILABLE.value,
                                fee_amount=fee_for_row(row, cap),
                            )
                        )
            if not missing:
                return
            db.session.add_all(missing)
            from ..services.audit_service import AuditService

            AuditService.record(
                "MARKET_GRID_PROVISIONED",
                actor="system",
                entity_type="system",
                entity_id=f"{GRID_ROWS}x{GRID_COLS}",
                details=(
                    f"Stand grid backfilled ({len(missing)} stand(s)); front row highest fee "
                    f"{fee_for_row(0, cap)}, back row {fee_for_row(GRID_ROWS - 1, cap)}."
                ),
            )
            db.session.commit()
            log.info("Stand grid backfilled: %s stand(s) added (front-row pricing).", len(missing))
        except Exception:  # tables not migrated yet — build step runs first
            db.session.rollback()
            import traceback

            log.warning(
                "Stand grid bootstrap skipped: database not ready yet.\n%s",
                traceback.format_exc(limit=3),
            )
