"""Dependency-free PDF generation for digital market permits.

Emits a small, valid PDF 1.4 document (one page, Helvetica text) built purely
from bytes — no third-party dependency. Only used for issued permits: the
council's backend must have verified the payment and completed the allocation
before this is reachable (the route enforces that).
"""
from __future__ import annotations

from datetime import datetime, timezone


def _escape(text: str) -> str:
    """Escape PDF string literals and drop anything outside Latin-1 text."""
    cleaned = (text or "").replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")
    return "".join(ch if (32 <= ord(ch) < 127) else ("'" if ch in "‘’" else "'") for ch in cleaned)


def build_permit_pdf(
    *,
    permit_code: str,
    vendor_name: str,
    vendor_nrc: str,
    stand_code: str,
    zone: str,
    fee_amount: str,
    currency: str,
    issued_at: datetime | None,
    market_name: str = "Lusaka City Market",
    council_name: str = "Pa Market",
) -> bytes:
    issued = issued_at.astimezone(timezone.utc) if issued_at else datetime.now(timezone.utc)
    issued_label = issued.strftime("%d %B %Y, %H:%M UTC")

    lines: list[tuple[str, int, int]] = [
        # (text, font, size) — font 0 = regular, 1 = bold, 2 = small grey
        (council_name, 1, 18),
        (f"{market_name} · Official digital market permit", 0, 10),
        ("", 0, 8),
        (f"Permit number: {permit_code}", 1, 13),
        ("", 0, 6),
        (f"Vendor: {vendor_name}", 0, 11),
        (f"NRC: {vendor_nrc}", 0, 11),
        (f"Stand: {stand_code}", 0, 11),
        (f"Zone: {zone}", 0, 11),
        (f"Stand levy: {currency} {fee_amount} (verified by the council backend)", 0, 10),
        (f"Issued: {issued_label}", 0, 10),
        ("", 0, 8),
        ("This permit was issued after the vendor completed the full application", 2, 8),
        ("record: application review, stand allocation offer, vendor acceptance,", 2, 8),
        ("handover confirmed by both the vendor and an authorised official, and a", 2, 8),
        ("payment verified with the provider. Verification of authenticity is", 2, 8),
        ("performed by the council against the permit number — this document alone", 2, 8),
        ("does not prove a valid grant.", 2, 8),
    ]

    font_size = {0: 11, 1: 16, 2: 8}
    y_start = 760
    row = 22
    ops: list[str] = []
    y = y_start
    for text, font, size in lines:
        if text:
            ops.append(f"BT /F{font + 1} {size} Tf 1 0 0 1 56 {y} Tm ({_escape(text)}) Tj ET")
        y -= max(row, size + 8)
    # a rules line under the header
    ops.append("0.4 0.4 0.4 RG 1 w 56 778 m 539 778 l S")
    # footer strip
    ops.append("0.08 0.24 0.25 RG 2 w 40 40 m 40 802 l S")
    content = "\n".join(ops).encode("latin-1", "replace")

    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
        b"/Resources << /Font << /F1 4 0 R /F2 5 0 R >> >> /Contents 6 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>",
        b"<< /Length " + str(len(content)).encode() + b" >>\nstream\n" + content + b"\nendstream",
    ]

    out = bytearray(b"%PDF-1.4\n%\xc7\xec\x8f\xa2\n")
    offsets: list[int] = []
    for index, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{index} 0 obj\n".encode() + body + b"\nendobj\n"
    xref_at = len(out)
    out += f"xref\n0 {len(objects) + 1}\n".encode()
    out += b"0000000000 65535 f \n"
    for offset in offsets:
        out += f"{offset:010d} 00000 n \n".encode()
    out += (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_at}\n%%EOF\n"
    ).encode()
    return bytes(out)
