# PaMarket — Database Schema

PostgreSQL (Neon) via SQLAlchemy; every listed table is created by the
Alembic migration `backend/migrations/versions/76819de08106_initial_pamarket_schema.py`.

Conventions shared by every table (from `models/base.py`):

| Column       | Type                    | Notes                                    |
| ------------ | ----------------------- | ---------------------------------------- |
| `id`         | `String(32)` PK         | pre-generated uuid4 hex (no DB round-trip needed before insert) |
| `created_at` | `TIMESTAMPTZ`           | UTC, default now                          |

Monetary columns are `NUMERIC(x,2)` mapped to Python `Decimal` — floats are
never used for money.

Foreign keys use explicit `ON DELETE` behaviour (CASCADE for owned children,
SET NULL for references that must survive deletion, RESTRICT where history is
sacred). Every FK column is indexed.

---

## users
Login identities for both vendors and council admins.

| Column          | Type          | Constraints |
| --------------- | ------------- | ----------- |
| `phone`         | `String(24)`  | UNIQUE, indexed — login identifier |
| `full_name`     | `String(120)` | NOT NULL |
| `password_hash` | `String(255)` | NOT NULL — Werkzeug scrypt, never plaintext |
| `role`          | `String(16)`  | indexed; `vendor` \| `admin` |
| `nrc`           | `String(32)`  | UNIQUE, nullable |
| `business_type` | `String(64)`  | nullable |
| `is_active`     | `Boolean`     | default true |
| `last_login_at` | `TIMESTAMPTZ` | nullable |

No admin-signup codes: admins are seeded server-side. Passwords hashed with a
recognised salted iterative scheme (scrypt).

## vendors
Vendor profile, 1:1 with a user (`user_id` UNIQUE FK → users, CASCADE), plus
queue state.

`nrc` UNIQUE, `full_name`, `phone`, `business_type` (default
`General Merchandise`), `preferred_zone`, `payment_method`
(`mtn|airtel|zamtel`), `queue_position`, `status`
(`registered → pending → …`), `applied_at` NOT NULL timestamp.

Relationships: `applications` (1:N, CASCADE delete), allocations via
allocations.vendor_id, `stands` backref from the occupied stand.

## stands
The interactive map grid.

| Column            | Type           | Notes |
| ----------------- | -------------- | ----- |
| `code`            | `String(24)`   | UNIQUE, indexed (`ST-001`) |
| `row` / `col`     | `Integer`      | grid coordinates |
| `zone`            | `String(32)`   | indexed; `Produce | Textiles | Hardware | Food Court` |
| `status`          | `String(16)`   | indexed; `available|reserved|occupied|maintenance` |
| `vendor_id`       | FK vendors     | SET NULL; current occupant |
| `vendor_name`/`vendor_nrc` | String | denormalised for map display (nrc indexed) |
| `allocated_at`, `hold_expires_at` | TIMESTAMPTZ | occupancy / offer-hold windows |
| `fee_amount`      | `Numeric(10,2)` | default 5.00 |
| `currency`        | `String(3)`    | default USD |

## applications
Queue records.

`vendor_id` FK CASCADE indexed, `stand_id` FK SET NULL (chosen stand when
practical), `status` indexed (`submitted|under_review|approved|allocated|rejected|cancelled`),
`queue_position` NOT NULL, `business_type`, `preferred_zone`, `notes` TEXT,
`reviewed_by` FK users SET NULL, `reviewed_at`, `decision_reason` (≤255).

One active application per vendor enforced in the service layer
(409 `application_exists`).

## allocations
The offer state machine.

| Column              | Type            | Notes |
| ------------------- | --------------- | ----- |
| `application_id`    | FK applications | CASCADE indexed |
| `stand_id`          | FK stands       | RESTRICT (history intact even if a stand were retired) |
| `vendor_id`         | FK vendors      | CASCADE indexed |
| `status`            | `String(24)`    | indexed; `offered|accepted|handover_confirmed|completed|cancelled|expired` |
| `offered_by`        | FK users        | SET NULL |
| `offered_at`        | TIMESTAMPTZ NOT NULL | |
| `accepted_at`       | TIMESTAMPTZ     | nullable |
| `offer_expires_at`  | TIMESTAMPTZ     | 48h after offer; expiry releases the stand |
| `fee_amount`        | `Numeric(10,2)` | snapshot of the stand fee at offer time |
| `currency`          | `String(3)`     | |
| `permit_code`       | `String(40)`    | UNIQUE, only set on completion |
| `completed_at`      | TIMESTAMPTZ     | |
| `cancelled_reason`  | `String(255)`   | |

## handover_confirmations
Dual-proof of physical handover.

`allocation_id` FK CASCADE, `role` (`vendor|official`),
**UNIQUE (`allocation_id`, `role`)** — one proof per side, no duplicates;
`confirmed_by` FK users SET NULL, `confirmed_at` NOT NULL,
`meeting_location` (≤160), `notes` TEXT.

## payments
Money rows. `allocation_id` FK CASCADE, `vendor_id` FK CASCADE, both indexed.

| Column                | Type            | Notes |
| --------------------- | --------------- | ----- |
| `amount`              | `Numeric(12,2)` | NOT NULL — Decimal only |
| `currency`            | `String(3)`     | NOT NULL |
| `status`              | `String(16)`    | indexed; `pending|successful|failed|refunded|disputed` |
| `provider`            | `String(24)`    | `devdraft-sandbox|devdraft-test|devdraft-live` |
| `provider_reference`  | `String(64)`    | UNIQUE indexed (`pay_…` from DevDraft) |
| `provider_status_raw` | `String(48)`    | last raw provider status |
| `idempotency_key`     | `String(64)`    | UNIQUE indexed — mirrors DevDraft `Idempotency-Key` |
| `receipt_no`          | `String(32)`    | UNIQUE (`PAM-YYYYMMDD-XXXXXXXX`) |
| `description`         | `String(255)`   | |
| `completed_at`, `receipt_issued_at` | TIMESTAMPTZ | |

## payment_events
Append-only audit trail for every provider interaction. Nothing here is ever
updated or deleted in application code.

`payment_id` FK CASCADE indexed, `event_type` (`payment_created_request`,
`provider_creation_response`, `status_sync`, `webhook:payment.completed`,
`refund`, `status_check_error`, …), `provider_event_id` UNIQUE indexed
(webhook dedupe key), `raw_status`, `payload` (**JSONB on Neon**, JSON on
other engines via a dialect variant), `signature_valid` (NULL = N/A).

## notifications
`user_id` FK CASCADE indexed, `type` (mirrors `constants.NotificationType`),
`title` (≤120), `message` TEXT, `payload` JSON/JSONB, `read` Boolean indexed.

## audit_logs
Tamper-evident chain: `action`, `actor`, `actor_role`, `entity_type` +
`entity_id` (indexed for lookup), `details` (≤500), `recorded_at` NOT NULL,
`prev_hash` (64 hex; NULL for the first entry), `entry_hash` (64 hex,
SHA-256 over the payload + previous hash). `GET /api/v1/audit-logs/verify`
recomputes the chain and reports the first broken entry.

## corruption_reports
Whistleblower submissions: `reference` UNIQUE (`WBR-…`), `category`,
`description` (≤2000), `location`, `contact_email`, `status`
(`received|under_review|resolved|dismissed`).

## chat_session / chat_message (Market Assistant — chatbot-owned)

Backing tables for the Market Assistant (Developer 3's chatbot package,
`backend/app/chatbot/`). They are **not** part of the Alembic chain: the
chatbot service creates them idempotently at startup with its own metadata
(`app/chatbot/models.py` + `database.py`) in the same database as the
application tables (Neon in production). Schema:

- `chat_session` — `id` (hex PK), identity snapshot (`kind` guest|verified,
  `user_id`, `user_name`, `user_phone`, `user_role`, `user_nrc`,
  `user_business_type`), `created_at`, `last_active_at`, `message_count`,
  `closed`.
- `chat_message` — int autoincrement PK; `session_id` FK CASCADE,
  `role` (`user|assistant|tool`), `content` TEXT, `tool_name`, `tool_payload`
  (JSON text trace), `verified`/`degraded` flags, `created_at`.

Deployment note: databases migrated with the *initial* scaffold before this
change may still contain the unused `chatbot_sessions`/`chatbot_messages`
tables — harmless leftovers, safe to drop manually.

---

## Mapping from the legacy Prisma schema

Everything in `prisma/schema.prisma` that carries business meaning was mapped:
users/vendors/stands/applications/audit tables exist with the same identifiers
(`nrc`, `code`, row/col grid, statuses). Notable upgrades: money moved from
int-cents/plain numbers into `Numeric` Decimals, allocations got their own
lifecycle table (the old app mutated stand+vendor in place), payment
attempts/events are new (the old app stored a single mock payment field), and
audit entries are now hash-chained instead of free-form rows.

## Migration commands (backend/)

```bash
.venv/bin/flask db init      # once
.venv/bin/flask db migrate -m "message"
.venv/bin/flask db upgrade
.venv/bin/flask seed-demo --yes   # local demo data only
```

`DATABASE_URL` decides the target: a Neon `postgresql://` URL in production,
local SQLite in development (the config layer refuses non-SQL URLs such as
the Prisma `file:` scheme and falls back to SQLite with a warning).
