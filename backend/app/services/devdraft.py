"""DevDraft payment provider adapters.

Three modes (set DEVDRAFT_MODE):

  "sandbox"  No credentials needed. Deterministic in-process mock, clearly
             labelled `provider=devdraft-sandbox`. Used for local dev + CI.
  "test"     Official DevDraft TEST-PAYMENT endpoints:
               POST /api/v0/test-payment            (Idempotency-Key header)
               GET  /api/v0/test-payment/{id}
               POST /api/v0/test-payment/{id}/refund
               docs: https://devdraft.ai/docs/api-reference/test-payments
  "live"     Official production payment-intents API:
               POST /api/v0/payment-intents/bank    (ACH / SEPA / WIRE)
               POST /api/v0/payment-intents/stablecoin
               GET  /api/v0/payment-intents/{txId}/status
               docs: https://devdraft.ai/docs/developers/payment-intents

Authentication (both test + live): every request carries
  x-client-key: <client key from the Devdraft Console>
  x-client-secret: <client secret>
State-changing calls also carry `Idempotency-Key` (a fresh UUID per operation,
never per retry). Reusing a key with different parameters returns 409.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
import threading
import uuid
from abc import ABC, abstractmethod
from decimal import Decimal
from typing import Any

import requests


class DevDraftError(Exception):
    def __init__(self, message: str, status: int = 502, code: str = "provider_error"):
        super().__init__(message)
        self.status = status
        self.code = code


class PaymentProvider(ABC):
    """Interface the rest of the backend codes against — never a concrete API."""

    mode: str = "abstract"

    @abstractmethod
    def create_payment(self, *, amount: Decimal, currency: str, description: str,
                       idempotency_key: str, customer_reference: str | None = None) -> dict:
        """Returns {"provider_reference", "provider_status_raw", "raw"}."""

    @abstractmethod
    def get_payment(self, provider_reference: str) -> dict:
        """Returns {"status_raw", raw}."""

    @abstractmethod
    def refund_payment(self, provider_reference: str, idempotency_key: str) -> dict:
        """Returns {"refund_reference", "status_raw", raw}."""

    @abstractmethod
    def verify_webhook(self, raw_body: bytes, signature: str | None) -> bool:
        """HMAC-SHA256 verification of the x-webhook-signature header."""


def normalize_status(raw: str | None) -> str:
    """Map DevDraft statuses (documented) to PaMarket payment states."""
    if not raw:
        return "pending"
    value = raw.strip().lower()
    pending = {"awaiting_funds", "in_review", "funds_received", "payment_submitted", "pending"}
    successful = {"payment_processed", "succeeded", "completed", "paid", "successful"}
    failed = {"payment_failed", "failed", "error", "undeliverable", "canceled", "cancelled", "expired"}
    refunded = {"refunded", "returned"}
    if value in successful:
        return "successful"
    if value in refunded:
        return "refunded"
    if value in failed:
        return "failed"
    if value == "disputed":
        return "disputed"
    if value in pending:
        return "pending"
    return "pending"


class SandboxDevDraftProvider(PaymentProvider):
    """Deterministic, credential-free mock. NEVER used in production.

    Behaviour contract (documented in docs/PAYMENT_FLOW.md):
      * amount <= 0                                  -> rejected
      * description contains the word "fail"        -> payment fails
      * description contains the word "refuse"      -> provider error
      * otherwise                                   -> immediately `succeeded`
    The webhook verification honours a locally configured signing secret so the
    full webhook path (including retries and replay) is exercised in tests.
    """

    mode = "sandbox"

    def __init__(self, webhook_secret: str):
        self.webhook_secret = webhook_secret
        self._store: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()

    # ------------------------------------------------------------------ helpers
    def _record(self, provider_reference: str, status: str, amount: Decimal, currency: str) -> dict:
        with self._lock:
            self._store[provider_reference] = {
                "id": provider_reference,
                "amount": float(amount),
                "currency": currency,
                "status": status,
                "timestamp": None,  # filled below to keep schema identical
            }
            return dict(self._store[provider_reference])

    # ---------------------------------------------------------------- interface
    def create_payment(self, *, amount: Decimal, currency: str, description: str,
                       idempotency_key: str, customer_reference: str | None = None) -> dict:
        reference = f"pay_sbx_{uuid.uuid4().hex[:12]}"
        if amount <= 0:
            raise DevDraftError("Amount must be positive.", 400, "invalid_amount")
        if "refuse" in description.lower():
            raise DevDraftError("Sandbox refused the payment request.", 502, "provider_unavailable")
        status = "failed" if "fail" in description.lower() else "succeeded"
        record = self._record(reference, status, amount, currency)
        return {"provider_reference": reference, "provider_status_raw": status, "raw": record}

    def get_payment(self, provider_reference: str) -> dict:
        with self._lock:
            record = self._store.get(provider_reference)
        if record is None:
            raise DevDraftError("Unknown sandbox payment reference.", 404, "not_found")
        return {"status_raw": record["status"], "raw": dict(record)}

    def refund_payment(self, provider_reference: str, idempotency_key: str) -> dict:
        record = self.get_payment(provider_reference)
        refund_id = f"ref_sbx_{uuid.uuid4().hex[:12]}"
        self._record(provider_reference, "refunded", Decimal(str(record["raw"]["amount"])), record["raw"]["currency"])
        return {
            "refund_reference": refund_id,
            "status_raw": "succeeded",
            "raw": {"id": refund_id, "paymentId": provider_reference, "status": "succeeded"},
        }

    def verify_webhook(self, raw_body: bytes, signature: str | None) -> bool:
        return _hmac_matches(raw_body, signature, self.webhook_secret)


def _hmac_matches(raw_body: bytes, signature: str | None, secret: str) -> bool:
    """DevDraft docs show BOTH `sha256=<hex>` (create-webhook Flask sample) and
    bare `<hex>` (webhook overview). Accept either, compare timing-safely."""
    if not signature or not secret:
        return False
    expected = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    candidate = signature[len("sha256="):] if signature.startswith("sha256=") else signature
    return hmac.compare_digest(candidate.lower(), expected.lower())


class DevDraftClient(PaymentProvider):
    """Real DevDraft API client (test + live modes). Not a mock."""

    mode = "test"  # overridden per instance

    def __init__(self, *, base_url: str, client_key: str, client_secret: str,
                 destination_network: str, destination_address: str,
                 timeout: float = 10.0, session: requests.Session | None = None):
        if not client_key or not client_secret:
            raise DevDraftError("DevDraft client key/secret missing from configuration.", 500, "misconfigured")
        self.base_url = base_url.rstrip("/")
        self.client_key = client_key
        self.client_secret = client_secret
        self.destination_network = destination_network
        self.destination_address = destination_address
        self.timeout = timeout  # DevDraft webhook callback timeout is 10s
        self._session = session or requests.Session()

    # ------------------------------------------------------------------ plumbing
    def _headers(self, idempotency_key: str | None = None) -> dict[str, str]:
        headers = {
            "x-client-key": self.client_key,
            "x-client-secret": self.client_secret,
            "Content-Type": "application/json",
        }
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key
        return headers

    def _request(self, method: str, path: str, *, idempotency_key: str | None = None,
                 payload: dict | None = None) -> dict:
        url = self.base_url + path
        response = self._session.request(
            method, url, headers=self._headers(idempotency_key),
            json=payload, timeout=self.timeout,
        )
        detail: dict | str
        try:
            detail = response.json() if response.content else {}
        except ValueError:
            detail = response.text[:500]
        if response.status_code >= 400:
            message = detail.get("message", "") if isinstance(detail, dict) else str(detail)
            raise DevDraftError(
                f"DevDraft returned {response.status_code}: {message or response.reason}",
                response.status_code if response.status_code >= 400 else 502,
            )
        if isinstance(detail, dict):
            return detail
        raise DevDraftError("DevDraft returned an unexpected response body.", 502)

    def verify_webhook(self, raw_body: bytes, signature: str | None) -> bool:
        from flask import current_app

        secret = current_app.config.get("DEVDRAFT_WEBHOOK_SECRET", "")
        return _hmac_matches(raw_body, signature, secret)

    # -------------------------------------------------------------- test mode
    def _create_test_payment(self, amount: Decimal, currency: str, description: str,
                             idempotency_key: str, customer_reference: str | None) -> dict:
        body: dict[str, Any] = {
            # documented PaymentRequestDto: number amount, currency, description
            "amount": float(amount),
            "currency": currency,
            "description": description,
        }
        if customer_reference:
            body["customerId"] = customer_reference
        data = self._request("POST", "/api/v0/test-payment", idempotency_key=idempotency_key, payload=body)
        return {
            "provider_reference": data["id"],
            "provider_status_raw": data.get("status", "succeeded"),
            "raw": data,
        }

    def _get_test_payment(self, provider_reference: str) -> dict:
        data = self._request("GET", f"/api/v0/test-payment/{provider_reference}")
        return {"status_raw": data.get("status"), "raw": data}

    def _refund_test_payment(self, provider_reference: str, idempotency_key: str) -> dict:
        data = self._request(
            "POST", f"/api/v0/test-payment/{provider_reference}/refund", idempotency_key=idempotency_key
        )
        return {
            "refund_reference": data.get("id"),
            "status_raw": data.get("status"),
            "raw": data,
        }

    # -------------------------------------------------------------- live mode
    def _create_bank_intent(self, amount: Decimal, currency: str, description: str,
                            idempotency_key: str, customer_reference: str | None) -> dict:
        if not self.destination_address:
            raise DevDraftError(
                "DEVDRAFT_DESTINATION_ADDRESS must be configured for live payment intents.",
                500, "misconfigured",
            )
        rail = {
            "USD": "ach_push",
            "EUR": "sepa",
        }.get(currency.upper(), "ach_push")
        body: dict[str, Any] = {
            "sourcePaymentRail": rail,
            "sourceCurrency": currency.lower(),
            "destinationCurrency": "usdc",
            "destinationNetwork": self.destination_network,
            "destinationAddress": self.destination_address,
            "amount": f"{amount:.2f}",  # documented as string
            "description": description,
        }
        if customer_reference:
            body["ach_reference"] = customer_reference[:10]
        data = self._request("POST", "/api/v0/payment-intents/bank", idempotency_key=idempotency_key, payload=body)
        return {
            "provider_reference": data["id"],
            "provider_status_raw": data.get("state", "awaiting_funds"),
            "raw": data,
        }

    def _get_intent_status(self, provider_reference: str) -> dict:
        data = self._request("GET", f"/api/v0/payment-intents/{provider_reference}/status")
        return {"status_raw": data.get("status"), "raw": data}

    # ------------------------------------------------------------- dispatch
    def create_payment(self, *, amount: Decimal, currency: str, description: str,
                       idempotency_key: str, customer_reference: str | None = None) -> dict:
        if self.mode == "test":
            return self._create_test_payment(amount, currency.upper(), description, idempotency_key, customer_reference)
        return self._create_bank_intent(amount, currency.upper(), description, idempotency_key, customer_reference)

    def get_payment(self, provider_reference: str) -> dict:
        if self.mode == "test":
            return self._get_test_payment(provider_reference)
        return self._get_intent_status(provider_reference)

    def refund_payment(self, provider_reference: str, idempotency_key: str) -> dict:
        if self.mode != "test":
            # The fetched DevDraft references document refunds only for the
            # /test-payment endpoints. Live intents document refund states
            # (REFUNDED/RETURNED) but no refund call was found in the
            # published reference — surface this honestly instead of guessing.
            raise DevDraftError(
                "Refunds are only supported against the DevDraft test-payment API; "
                "live-mode refunds must follow DevDraft's refund procedure/support.",
                409, "refund_unsupported_in_mode",
            )
        return self._refund_test_payment(provider_reference, idempotency_key)


def get_provider() -> PaymentProvider:
    """Factory resolved from config: sandbox | test | live.

    The provider is cached per app instance so the sandbox provider keeps its
    in-memory payment records across requests (otherwise a status check or
    refund would fail with "unknown reference" simply because a new instance
    was created per call).
    """
    from flask import current_app

    app = current_app._get_current_object()
    cache = app.extensions.setdefault("pamarket_providers", {})
    provider = cache.get("devdraft")
    if provider is not None:
        return provider

    mode = app.config["DEVDRAFT_MODE"]
    webhook_secret = app.config.get("DEVDRAFT_WEBHOOK_SECRET", "")
    if mode == "sandbox":
        provider = SandboxDevDraftProvider(webhook_secret)
    else:
        provider = DevDraftClient(
            base_url=app.config["DEVDRAFT_BASE_URL"],
            client_key=app.config["DEVDRAFT_CLIENT_KEY"],
            client_secret=app.config["DEVDRAFT_CLIENT_SECRET"],
            destination_network=app.config.get("DEVDRAFT_DESTINATION_NETWORK", "base"),
            destination_address=app.config.get("DEVDRAFT_DESTINATION_ADDRESS", ""),
        )
        provider.mode = "live" if mode == "live" else "test"
    cache["devdraft"] = provider
    return provider


def generate_receipt_number() -> str:  # pragma: no cover - trivial
    return f"PAM-{secrets.token_hex(4).upper()}"
