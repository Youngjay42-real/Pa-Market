# PaMarket Backend (Flask)

Developer 1 (Backend Lead) owns this folder. The backend is fully independent
of the Next.js frontend: it exposes a versioned REST API under `/api/v1`,
stores data in PostgreSQL (Neon in production / local SQLite in development)
and integrates the DevDraft payment API server-side.

```
backend/
├── app/
│   ├── __init__.py     # app factory (+ /healthz)
│   ├── config.py       # env-driven configuration (Neon, DevDraft, money limits)
│   ├── constants.py    # zones/categories/statuses (mirrors src/constants)
│   ├── errors.py       # stable error envelope
│   ├── extensions.py   # SQLAlchemy, Migrate, JWT, CORS, rate limiter
│   ├── models/         # User, Vendor, Stand, Application, Allocation,
│   │                   # HandoverConfirmation, Payment, PaymentEvent,
│   │                   # Notification, AuditLog, CorruptionReport, Chatbot*
│   ├── routes/         # auth, stands, applications, allocations, payments,
│   │                   # audit-logs, notifications, reports  (chatbot → Dev 3)
│   ├── services/       # auth, allocation state machine, payment orchestration,
│   │                   # devdraft adapter, hash-chained audit, notifications
│   └── utils/          # validation + `flask seed-demo`
├── migrations/         # Alembic (initial migration provisions every table)
├── tests/              # pytest suite (chatbot tests reserved for Dev 3)
├── requirements.txt
└── wsgi.py             # Gunicorn entrypoint + `flask` CLI
```

## Quickstart

```bash
cd backend
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

# optional local demo database (SQLite, no credentials needed)
.venv/bin/flask db upgrade        # run migrations
.venv/bin/flask seed-demo --yes   # admin 0776596009/1234567, vendor 0977123456, 96 stands

.venv/bin/flask run --debug       # http://localhost:5001/healthz
```

Tests:

```bash
.venv/bin/python -m pytest         # 22 tests, isolated SQLite per test
```

Production: see `../render.yaml` (Neon `DATABASE_URL`, JWT secrets, DevDraft
credentials via Render env vars — nothing committed).

## API surface

- `POST /auth/signup | login | logout`, `GET /auth/me` (JWT bearer, RBAC vendor/admin)
- `GET /stands[, /stats, /available, /meta, /{id|code}]` (public map data)
- `POST /applications`, `/applications/{id}/review` (queue + human review)
- `/allocations` create/auto-assign → accept → dual handover → eligibility → permit
- `/payments` initiate (Idempotency-Key), status (server-verified), receipt,
  webhook/devdraft (HMAC verified), refund (admin), team/limits
- `/audit-logs[+verify]`, `/notifications`, `/reports` (whistleblower)

Full request/response contract: `../docs/API_CONTRACT.md`.
Money-safety rules and the verified payment flow: `../docs/PAYMENT_FLOW.md`.

## DevDraft modes

`DEVDRAFT_MODE=sandbox|test|live` — see `../docs/PAYMENT_FLOW.md` §3. Sandbox
needs no credentials; `test` uses the official DevDraft test-payment API;
`live` uses the documented bank payment-intents API and refuses to run without
a destination address.

## Chatbot

`ChatbotSession`/`ChatbotMessage` models exist; routes and service logic are
owned by Developer 3 (`backend/app/chatbot/`, `backend/app/routes/chatbot.py`,
`backend/tests/chatbot/`, `docs/CHATBOT_CONTRACT.md`). Nothing implemented
here — deliberately left empty to avoid conflicts.
