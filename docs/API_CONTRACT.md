# PaMarket — REST API Contract (v1)

Base URL: `{host}/api/v1` (local dev: `http://localhost:5001/api/v1`)
Health endpoint (outside the prefix): `GET /healthz`

All request/response bodies are JSON. All errors return a stable envelope:

```json
{
  "error": { "code": "machine_readable_code", "message": "human readable" },
  "message": "human readable"
}
```

Common error codes: `unauthorized` (401), `forbidden` (403), `not_found` (404),
`invalid_state` (409), `rate_limited` (429), `internal_error` (500).

---

## Authentication

JWT bearer tokens (`Authorization: Bearer <token>`). Tokens carry `role`
claims (`vendor` | `admin`). Vendors self-register; **admin accounts are
provisioned server-side only** (`flask bootstrap-admin`, local `flask seed-demo`,
or backend lead) — there is no admin signup code.

| Method | Path       | Body                                        | Response (200/201)                                                              |
| ------ | ---------- | ------------------------------------------- | ------------------------------------------------------------------------------- |
| POST   | `/signup`  | `phone, full_name, password, nrc[, business_type]` | `{ token, token_type, expires_in, user{ id, phone, full_name, role, nrc, business_type } }` |
| POST   | `/login`   | `phone, password`                           | same shape as signup                                                            |
| POST   | `/logout`  | — (JWT auth)                                | `{ message }`. Client discards the token.                                       |
| GET    | `/me`      | —                                           | `{ id, phone, full_name, role, nrc, business_type, vendor_id, unread_notifications }` |

Validation rules (server-side, 400 with `details.fields` / `details.allowed`):
- `phone`: normalised to `09XXXXXXXX`; `+260…` accepted.
- `nrc`: `123456/78/1` (slashes required).
- `password`: min 8 chars.
- `business_type`: one of the 12 council categories (see `/stands/meta`).

---

## Stands (public market map)

| Method | Path         | Query                                     | Response |
| ------ | ------------ | ----------------------------------------- | -------- |
| GET    | `/stands`    | `zone, status, q, limit`                  | `{ stands: [ { id, code, row, col, zone, status, vendor_name, vendor_nrc*, allocated_at, hold_expires_at, fee_amount, currency } ] }` |
| GET    | `/stands/stats` | —                                      | `{ zones: [ { zone, counts: {available,reserved,occupied,maintenance}, total } ], occupied_vendors }` |
| GET    | `/stands/available` | —                                  | `{ stands: [...] }` (available only) |
| GET    | `/stands/meta` | —                                       | `{ zones, business_categories, category_zones }` |
| GET    | `/stands/{id_or_code}` | —                               | single stand (`vendor_nrc` only visible to admins) |

`status` ∈ `available | reserved | occupied | maintenance`.

---

## Applications

| Method | Path                        | Who    | Notes |
| ------ | --------------------------- | ------ | ----- |
| POST   | `/applications`             | vendor | Body `{ business_type, preferred_zone?, notes? }` → 201 application. One active application per vendor (409 `application_exists`). |
| GET    | `/applications/mine`        | vendor | `{ applications: [...] }`, newest first, each with `allocation_id` when allocated. |
| GET    | `/applications`             | admin  | Queue; query `?status=`. Includes embedded `vendor` object. |
| GET    | `/applications/{id}`        | admin or owning vendor | detail |
| POST   | `/applications/{id}/review` | admin  | Body `{ decision: "approved"|"rejected", reason? }`. Human decision required — no automatic approvals. |

Application statuses: `submitted → approved | rejected`, plus `under_review`,
`cancelled`; an application that received a stand becomes `allocated`.

---

## Allocations (the core state machine)

```
offered ──(vendor accepts)──► accepted ──(vendor + official confirm)──► handover_confirmed
   │  (48h expiry or admin cancel)                                        │
   ▼                                                                      ▼
expired / cancelled                                              completed (payment verified → permit issued)
```

| Method | Path                            | Who    | Notes |
| ------ | ------------------------------- | ------ | ----- |
| POST   | `/allocations`                  | admin  | Body `{ application_id, stand_id? , auto_assign? }` — `auto_assign: true` picks the best stand by zone scoring (+10 zoned-suited, +20 preferred zone). Stand → `reserved`. Offer expires in 48h. |
| GET    | `/allocations`                  | admin  | list, `?status=` |
| GET    | `/allocations/mine`             | vendor | own allocations |
| GET    | `/allocations/{id}`             | admin or owning vendor | detail incl. `handover` confirmation timestamps |
| POST   | `/allocations/{id}/accept`      | owning vendor | `offered → accepted`. 410 `offer_expired` after the deadline (stand released). |
| POST   | `/allocations/{id}/handover`    | vendor(own) or admin | role inferred from JWT. First side records `accepted`-state confirmation; when BOTH sides confirm the allocation becomes `handover_confirmed`. Body `{ meeting_location?, notes? }`. Unique per role (409 `already_confirmed`). |
| GET    | `/allocations/{id}/eligibility` | admin or owning vendor | `{ allocation_id, eligible, reasons: [...] }` — the single source of truth for "can this be paid now?" |
| GET    | `/allocations/{id}/permit`      | admin or owning vendor | permit JSON `{ permit_code, stand_code, zone, vendor_name, vendor_nrc, issued_at }`; 409 `permit_unavailable` until payment is verified. |

---

## Payments (DevDraft)

Rules enforced server-side (never by the frontend):
1. Amount always comes from DB records (allocation fee) — the request body
   cannot set an amount.
2. Eligibility is re-verified at initiation (`payment_not_eligible` 409 with
   `details.reasons` otherwise).
3. `Idempotency-Key` header REQUIRED: 6–64 alphanumeric chars (+ `-`/`_`).
   Replaying the same key returns the same payment instead of double-charging.
4. Hackathon limits: max **$5.00** per transaction, max **$50.00** cumulative
   successful+pending team volume (`PAYMENT_MAX_*` env, configurable).
5. Never assume success from a button click — the backend verifies with the
   provider (`status` sync) or a signature-verified webhook.

| Method | Path                             | Who    | Notes |
| ------ | -------------------------------- | ------ | ----- |
| POST   | `/payments/initiate`             | admin or owning vendor | Body `{ allocation_id }`, header `Idempotency-Key`. 201 payment. |
| GET    | `/payments/history`              | admin (all) / vendor (own) | `?status=` |
| GET    | `/payments/{id}`                 | admin or owning vendor | detail |
| GET    | `/payments/{id}/status`          | admin or owning vendor | **server-side provider verification**; persists provider status. |
| GET    | `/payments/{id}/receipt`         | admin or owning vendor | full receipt + payment event trail (409 before success). |
| POST   | `/payments/webhook/devdraft`     | public | DevDraft → backend. Header `x-webhook-signature` (HMAC-SHA256 of raw body; `sha256=`-prefixed and bare hex both accepted). Idempotent by event id; 200 fast. |
| POST   | `/payments/{id}/refund`          | admin  | Body `{ reason? }`. Hackathon rule: refund test transactions before the 3:30 PM CAT deadline. Refund resets allocation → `cancelled` and frees the stand. |
| GET    | `/payments/team/limits`          | admin  | `{ currency, spent_so_far, remaining, max_per_transaction, max_team_total }` |

Payment statuses: `pending → successful | failed`, `refunded`, `disputed`.
On success backend issues `receipt_no` (`PAM-YYYYMMDD-XXXXXXXX`), sets the
allocation to `completed`, generates `permit_code` (`PAM-PERMIT-…`), and marks
the stand `occupied`.

Provider modes (`DEVDRAFT_MODE` env): `sandbox` (labelled mock, no
credentials), `test` (official DevDraft test-payment API), `live` (official
bank payment-intents API). See `docs/PAYMENT_FLOW.md`.

---

## Audit logs

| Method | Path                    | Who   | Notes |
| ------ | ----------------------- | ----- | ----- |
| GET    | `/audit-logs`           | admin full, vendor own-entities only | `?limit&offset&entity_type&entity_id` → `{ logs, total }`. Entries are hash-chained (`prev_hash → entry_hash`). |
| GET    | `/audit-logs/verify`    | admin | `{ valid, entries }` or `{ valid: false, broken_index, reason }` |

---

## Notifications

| Method | Path                          | Who  | Notes |
| ------ | ----------------------------- | ---- | ----- |
| GET    | `/notifications`              | any authed user | `?unread_only=true` → `{ notifications, unread }` |
| POST   | `/notifications/{id}/read`    | owner |   |

---

## Whistleblower reports

| Method | Path                      | Who   | Notes |
| ------ | ------------------------- | ----- | ----- |
| POST   | `/reports`                | public (rate-limited) | Body `{ category, description (≥10 chars), location?, contact_email? }`. Categories: `bribe_request, favouritism, fake_documents, dupe_application, other`. Returns pseudonymous `{ reference }` (e.g. `WBR-261031-4F2A9C`). |
| GET    | `/reports`                | admin | list `?status=` |
| POST   | `/reports/{id}/status`    | admin | `received | under_review | resolved | dismissed` |

---

## Chatbot (`/chatbot/*`)

Implemented by the backend team — full request/response shapes in
`docs/CHATBOT_CONTRACT.md` (§14 covers the PaMarket schema adaptation).

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/api/v1/chatbot/health` | Assistant status + LLM provider label (`mock` when unconfigured) |
| POST | `/api/v1/chatbot/sessions` | Create session (verified identity or guest); returns signed `chatToken` |
| POST | `/api/v1/chatbot/sessions/{id}/messages` | Send a user turn; returns user + assistant messages with `meta` |
| GET | `/api/v1/chatbot/sessions/{id}/messages` | Transcript replay (user/assistant only) |
| POST | `/api/v1/chatbot/sessions/{id}/close` | Close a session |

Auth model: sessions verify identity against stored `users` rows once, then use
short-lived signed chat tokens (Bearer) — independent of backend JWTs. The
assistant is read-only over application data; admin-only tools return structured
`{denied: true}` payloads for non-admins.
