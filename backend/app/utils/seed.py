"""Demo data seeder (`flask seed-demo`) — only for local development.

Creates the council admin, a demo vendor, the full 8x12 stand grid and an
audit entry, mirroring the previous mock data so the interactive map still
has interesting content. Guarded behind an explicit --yes flag.
"""
import click
from datetime import datetime, timedelta, timezone

from ..constants import MARKET_ZONES, StandStatus
from ..extensions import db
from ..models import Stand
from ..services.audit_service import AuditService


def _zone_for_col(col: int) -> str:
    return list(MARKET_ZONES)[(col // 3) % len(MARKET_ZONES)]


def _ensure_admin(phone: str, password: str) -> None:
    from ..models import User

    if db.session.query(User).filter_by(phone=phone).one_or_none() is None:
        from ..services.auth_service import hash_password

        db.session.add(
            User(
                phone=phone,
                full_name="Council Administrator",
                password_hash=hash_password(password),
                role="admin",
            )
        )
        click.echo(f"admin user {phone} created")


def _ensure_vendor(phone: str, password: str) -> None:
    from ..models import User, Vendor

    vendor = db.session.query(Vendor).filter_by(nrc="123456/78/1").one_or_none()
    if vendor is not None:
        return
    user = db.session.query(User).filter_by(phone=phone).one_or_none()
    if user is None:
        from ..services.auth_service import hash_password

        user = User(
            phone=phone,
            full_name="Mary Banda",
            password_hash=hash_password(password),
            role="vendor",
            nrc="123456/78/1",
        )
        db.session.add(user)
        db.session.flush()
    vendor = Vendor(
        user_id=user.id,
        nrc="123456/78/1",
        full_name="Mary Banda",
        phone=phone,
        queue_position=1,
        status="pending",
        applied_at=datetime.now(timezone.utc),
    )
    db.session.add(vendor)
    click.echo("vendor 0977123456 created (Mary Banda)")


def _ensure_stands() -> None:
    if db.session.query(Stand).count() > 0:
        return
    index = 0
    week_ago = datetime.now(timezone.utc) - timedelta(days=7)
    for row in range(8):
        for col in range(12):
            index += 1
            roll = (row * 12 + col) % 10
            status = (
                StandStatus.OCCUPIED if roll < 4
                else StandStatus.RESERVED if roll == 4
                else StandStatus.MAINTENANCE if roll == 5
                else StandStatus.AVAILABLE
            )
            occupied = status == StandStatus.OCCUPIED
            db.session.add(
                Stand(
                    code=f"ST-{index:03d}",
                    row=row,
                    col=col,
                    zone=_zone_for_col(col),
                    status=status.value,
                    vendor_name=f"Vendor {index}" if occupied else None,
                    vendor_nrc=f"123456/{index:02d}/1" if occupied else None,
                    allocated_at=week_ago if occupied else None,
                )
            )
    click.echo("stand grid 8x12 created")


def register_seed_command(app) -> None:
    @app.cli.command("seed-demo")
    @click.option("--admin-phone", default="0776596009", show_default=True)
    @click.option("--admin-password", default="1234567", show_default=True)
    @click.option("--vendor-phone", default="0977123456", show_default=True)
    @click.option("--vendor-password", default="pass123", show_default=True)
    @click.option("--yes", is_flag=True, help="Write demo rows (required confirmation).")
    def seed_demo(admin_phone: str, admin_password: str, vendor_phone: str,
                  vendor_password: str, yes: bool) -> None:
        """Seed demo data for local development."""
        if not yes:
            click.echo("Refusing to write demo data without --yes.")
            return
        if not app.config.get("ALLOW_DEMO_SEED"):
            click.echo("Seeding disabled via ALLOW_DEMO_SEED in this environment.")
            return

        _ensure_admin(admin_phone, admin_password)
        _ensure_vendor(vendor_phone, vendor_password)
        _ensure_stands()

        AuditService.record(
            "DEMO_SEED",
            actor="system",
            entity_type="system",
            entity_id="seed-demo",
            details="Demo dataset seeded via flask seed-demo.",
        )
        db.session.commit()
        click.echo("demo seed complete — admin 0776596009 / vendor 0977123456")
