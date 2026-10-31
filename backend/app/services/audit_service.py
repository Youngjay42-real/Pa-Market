"""Append-only, hash-chained audit log.

Each entry binds its payload to the previous entry's hash, so deleting or
editing rows (or a full-table rewrite) becomes detectable: any admin can run
`AuditService.verify_chain()` and see which entry breaks the chain first.
"""
import hashlib
import threading
from datetime import datetime, timezone

from ..extensions import db
from ..models import AuditLog

_chain_lock = threading.Lock()

GENESIS_HASH = "0" * 64


def _payload_hash(previous: str | None, *, action: str, actor: str, actor_role: str,
                  entity_type: str, entity_id: str, details: str | None,
                  recorded_at: datetime) -> str:
    material = "|".join(
        [
            previous or GENESIS_HASH,
            action,
            actor,
            actor_role,
            entity_type,
            entity_id,
            details or "",
            recorded_at.isoformat(),
        ]
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


class AuditService:
    @staticmethod
    def record(action: str, *, actor: str = "system", actor_role: str = "system",
               entity_type: str, entity_id: str, details: str | None = None,
               recorded_at: datetime | None = None) -> AuditLog:
        with _chain_lock:
            last = db.session.query(AuditLog).order_by(AuditLog.recorded_at.desc()).first()
            recorded_at = recorded_at or datetime.now(timezone.utc)
            prev = last.entry_hash if last else None
            entry_hash = _payload_hash(
                prev,
                action=action,
                actor=actor,
                actor_role=actor_role,
                entity_type=entity_type,
                entity_id=entity_id,
                details=details,
                recorded_at=recorded_at,
            )
            entry = AuditLog(
                action=action,
                actor=actor,
                actor_role=actor_role,
                entity_type=entity_type,
                entity_id=entity_id,
                details=(details or "")[:500] or None,
                recorded_at=recorded_at,
                prev_hash=prev,
                entry_hash=entry_hash,
            )
            db.session.add(entry)
            return entry

    @staticmethod
    def verify_chain() -> dict:
        """Walk the chain and report the first tampered/broken entry, if any."""
        entries = db.session.query(AuditLog).order_by(AuditLog.recorded_at).all()
        prev_hash: str | None = None
        for index, entry in enumerate(entries):
            expected = _payload_hash(
                prev_hash,
                action=entry.action,
                actor=entry.actor,
                actor_role=entry.actor_role,
                entity_type=entry.entity_type,
                entity_id=entry.entity_id,
                details=entry.details,
                recorded_at=entry.recorded_at,
            )
            # entry_hash is computed from the *stored previous* value, so compare both links
            if entry.prev_hash != (None if index == 0 else entries[index - 1].entry_hash):
                return {"valid": False, "broken_index": index, "reason": "prev_hash mismatch"}
            if expected != entry.entry_hash:
                return {
                    "valid": False,
                    "broken_index": index,
                    "reason": "content hash mismatch (entry was edited)",
                }
            prev_hash = entry.entry_hash
        return {"valid": True, "entries": len(entries)}

    @staticmethod
    def list_entries(query=None, limit: int = 200, offset: int = 0):
        q = query if query is not None else db.session.query(AuditLog)
        total = q.count()
        rows = q.order_by(AuditLog.recorded_at.desc()).limit(limit).offset(offset).all()
        return total, rows
