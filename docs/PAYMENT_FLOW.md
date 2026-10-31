# PaMarket — Payment Flow (DevDraft)

> **The rule the whole product stands on: money only moves after the
> allocation AND the physical handover have been verified by two independent
> parties.** No button click, page redirect or frontend state can mark a
> payment as received.

---

## 1. The gate: payment eligibility

`AllocationService.eligibility()` (backed by `PaymentConditions`, so the same
rules drive both "can pay" checks and the actual payment run) returns
`{ eligible: bool, reasons: [...] }`. A payment can only be initiated when:

1. allocation status = `handover_confirmed`
   (vendor confirmed **and** a council official confirmed — two rows in
   `handover_confirmations`, unique per role), and
2. no open (`pending`/`successful`) payment already exists for the
   allocation, and
3. the amount ≤ `PAYMENT_MAX_PER_TRANSACTION` (**$5.00** hard cap for the
   hackathon), and
4. cumulative `pending + successful` volume + amount ≤
   `PAYMENT_MAX_TEAM_TOTAL` (**$50.00** team cap).

Any reason being present → 409 `payment_not_eligible` with `details.reasons`.
`GET /api/v1/allocations/{id}/eligibility` exposes the same verdict to the UI.

## 2. What the client is allowed to send

`POST /api/v1/payments/initiate` with `{ "allocation_id": "…" }` and the
`Idempotency-Key` header. **The amount is never in the request** — it is read
from the allocation (which snapshot the stand fee at offer time). Failed:
400 (`idempotency_key_required|invalid`), 409 (`payment_not_eligible`,
`idempotency_conflict`), 502 (`provider_unavailable` — with the guarantee
*no money moved*).

## 3. Provider integration (official DevDraft API only)

Base URL `https://api.devdraft.ai`. Authentication on every request (per
devdraft.ai docs — "API Request Authentication"):

```
x-client-key: <client key from the Devdraft Console>
x-client-secret: <client secret>
```

Both headers are required. Secrets live in environment variables
(`DEVDRAFT_CLIENT_KEY/SECRET`) — never in the browser bundle or git.

### Modes (`DEVDRAFT_MODE`)

| Mode     | Endpoints used (documented) | Credentials | Use |
| -------- | --------------------------- | ----------- | --- |
| `sandbox` | in-process adapter (labelled `devdraft-sandbox`) | none | local dev, CI, demo |
| `test`    | `POST /api/v0/test-payment`, `GET /api/v0/test-payment/{id}`, `POST /api/v0/test-payment/{id}/refund` | console key pair | hackathon demo against DevDraft test rails |
| `live`    | `POST /api/v0/payment-intents/bank` (ACH/SEPA/WIRE), `GET /api/v0/payment-intents/{txId}/status` | console key pair | real deployment only |

For `live`, the body follows the documented bank-intent schema
(`sourcePaymentRail`, `sourceCurrency`, `destinationCurrency: usdc`,
`destinationNetwork`, `destinationAddress`, `amount` **as string**) and
`DEVDRAFT_DESTINATION_ADDRESS` must be configured or the backend refuses to
call the API.

### Idempotency (per devdraft.ai "Idempotency" docs)

A fresh UUID per **operation** (not per retry) in `Idempotency-Key`
(6–64 alphanumeric). Same key + same params → provider returns the original
result; same key + different params → 409 Conflict, which the backend surfaces
as `idempotency_conflict`. The key is persisted on the payment row, so local
replays are handled without even hitting the provider.

### Status mapping (`normalize_status`)

| DevDraft raw | PaMarket |
| ------------ | -------- |
| `awaiting_funds`, `in_review`, `funds_received`, `payment_submitted` | `pending` |
| `payment_processed`, `succeeded`, `completed` | `successful` |
| `payment_failed`, `failed`, `expired`, `canceled` | `failed` |
| `refunded`, `returned` | `refunded` |
| unknown | `pending` (never optimistically "successful") |

## 4. Verification — the backend, not the browser, decides

Two independent confirmation channels, both funnel through the same
`_mark_successful` path (receipt number, permit, stand occupancy, audit
entry):

1. **Status sync** — `GET /api/v1/payments/{id}/status` calls the provider's
   documented status endpoint server-side and stores every response.
2. **Webhook** — `POST /api/v1/payments/webhook/devdraft` verifies
   `x-webhook-signature` as HMAC-SHA256 over the **raw** request body with
   `DEVDRAFT_WEBHOOK_SECRET` (devdraft.ai webhook overview sample). Both the
   bare-hex and the `sha256=<hex>` prefixed forms shown in DevDraft's docs are
   accepted — compared timing-safely (`hmac.compare_digest`). Invalid
   signatures: 401, body still never trusted.

Webhook retries are safe: DevDraft retries with backoff, the backend deduplicates by
`evt.id` (`provider_event_id` UNIQUE in `payment_events`) and answers `200`
`duplicate_ignored` immediately. Unknown provider objects are acknowledged
without any financial side effect.

## 5. On success

`_mark_successful`:
- `receipt_no` = `PAM-YYYYMMDD-<8 hex>`, `receipt_issued_at` set
- allocation → `completed`, `permit_code` = `PAM-PERMIT-<12 hex>`
- stand → `occupied`, vendor stamped on it
- notification pushed to the vendor; audit entry
  `PAYMENT_VERIFIED_SUCCESSFUL` appended to the hash chain

Receipt (with the full event trail incl. signature validity) at
`GET /api/v1/payments/{id}/receipt`; permit at
`GET /api/v1/allocations/{id}/permit`.

## 6. Failure / refund

- `failed` (creation error or provider verdict): notification
  "No money moved — please try again", audit entry, no receipt.
- Admin `POST /payments/{id}/refund` refunds via the documented test-payment
  refund endpoint (idempotency key `refund_{payment}_{rand}`), then sets the
  payment `refunded`, cancels the allocation, revokes the permit and frees the
  stand. Audit `PAYMENT_REFUNDED`.
- **Live-mode refunds are honestly unsupported by the documented API surface**
  (their reference documents refund *states* but no refund endpoint for
  payment-intents) — the backend raises 409 `refund_unsupported_in_mode`
  instead of pretending. For the hackathon, refund deadlines are met in
  `test` mode before 3:30 PM CAT.
- Live-mode note: bank intents settle in hours/days; a pending live payment
  simply waits for verification (sync/webhook). Nothing completes early.

## 7. What is *not* claimed

This is **not** escrow: the backend does not hold funds. DevDraft moves the
money; PaMarket only *gates when it asks DevDraft to move it* and *verifies
what actually moved* — via status checks and signed webhooks only.

## 8. Sandbox behaviour contract (for tests/demo)

Deterministic, no network: description containing `fail` → failed payment;
`refuse` → provider error; otherwise immediate `succeeded`.
The sandbox honours `DEVDRAFT_WEBHOOK_SECRET` so the full webhook signature
path is testable without credentials; per-app provider state survives across
requests within one process (needed for status-sync and refund demos).
