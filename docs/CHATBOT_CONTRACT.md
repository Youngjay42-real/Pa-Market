# StandProof Chatbot Contract — "Market Assistant"

**Owner:** Developer 3 (AI Chatbot Engineer)
**Status:** v1.0 (2026-10-31)
**Consumers:** Flask backend chatbot service, Next.js chat widget, frontend lead, backend lead.

This document is the single source of truth for the chatbot feature. Any change to
request/response shapes, tool schemas or permission rules must be reflected here first,
before code changes.

---

## 1. Product intent

The Market Assistant is an AI chatbot inside StandProof that helps **vendors** and
**authorised administrators** understand and navigate the market allocation system.

Hard guarantees (enforced server-side, never by the LLM):

1. **Read-only.** The assistant has *no* write tools. It cannot submit applications,
   allocate stands, collect or confirm payments, generate permits, or edit any record.
   Requests for those actions get a refusal plus a pointer to the right page/person.
2. **Permission-scoped.** A vendor can only ever retrieve their **own** records. The
   scoping key (`user_id`, `nrc`) is bound to the verified session server-side — it is
   never accepted from the client per-request. Guests get public market information only.
3. **Verified vs explained.** Every assistant reply is labelled: answers produced from
   database tool results are marked `meta.verified = true`; general explanations without
   a database lookup are marked `meta.verified = false`. The assistant must never invent
   application statuses, payment results or market policy.
4. **Grounded honesty.** If the user asks something the assistant cannot verify, it says
   so and offers what it *can* do.
5. **No secrets.** Assistant replies never contain other vendors' personal data
   (phone, NRC), payment credentials or internal system identifiers beyond what is
   needed for the user's own records.
6. **No payment/allocation decisions.** The assistant cannot approve allocations,
   verify payments, or initiate payments. Those actions require an authorised human.

---

## 2. Architecture

```text
Next.js chat widget  ──HTTP──▶  Flask /api/v1/chatbot/*  ──▶  ChatbotService
     (src/components/chatbot)        (routes/chatbot.py)          │
                                              │                   ├─ identity.py   (identity verification + signed chat tokens)
                                              │                   ├─ permissions.py (role capability checks)
                                              │                   ├─ gateway.py    (permission-scoped READ-ONLY queries)
                                              │                   ├─ tools.py      (tool schemas + registry)
                                              │                   ├─ llm.py        (structured tool-calling provider + labelled mock)
                                              │                   ├─ prompts.py    (grounding system prompts)
                                              │                   ├─ service.py    (turn orchestration + persistence)
                                              │                   └─ models.py     (chat_session, chat_message)
                                              └────────────────▶ Shared database (Neon Postgres in production;
                                                                  same SQLite file as the app in local dev)
```

- The chatbot service is the **only** component with chatbot intelligence. The Next.js
  app contains **no** chatbot business logic — only the visual widget and an API client
  that follows this contract.
- In local development the widget calls same-origin `/api/v1/chatbot/*`, which
  `next.config.mjs` rewrites to Flask when `FLASK_API_URL` is set. In production the
  widget calls the Render Flask origin directly (`NEXT_PUBLIC_API_URL`).

---

## 3. Identity model

Every chat session is bound to one identity, created once and never changed:

| Kind | Verified against database | Data access |
| --- | --- | --- |
| `guest` | None (no identity supplied) | Public market info only |
| `verified` | `phone` + `fullName` + `role` (+ `nrc` when user has one) must all match a single `User` row | Own personal records; admins get aggregate views |

**Why not a password?** The widget does not (and must not) receive the user's password.
Instead the assistant verifies that the presented profile matches a real account row.
Forging another vendor's identity would require knowing their registered full name,
phone and NRC at once. This is consistent with the current app's auth model and is
**scheduled for replacement** by the backend lead's JWT identity provider (Flask
JWT-Extended) — see §12 Hardening. When that lands, the chatbot service swaps
`identity.verify_identity(...)` for JWT validation and nothing else changes.

**Rules:**
- Verification failures return an *identical* generic error for every reason (no user
  enumeration): `401 identity_invalid`.
- Role escalation is impossible: a user claiming `role: "admin"` must match the `User`
  row's stored role.
- Sessions and messages store the identity but never passwords.

---

## 4. Endpoints

Base URL: `<FLASK>/api/v1/chatbot`. All bodies are JSON (`Content-Type: application/json`).

### 4.1 `GET /health`

Public. No identity. Used by the widget to show online/offline status.

```json
{ "status": "ok", "assistant": { "name": "Market Assistant", "llmProvider": "mock" } }
```

### 4.2 `POST /sessions` — create a chat session

Request:

```json
{
  "identity": {                       // omit entirely for a guest session
    "phone": "0977123456",
    "fullName": "Mary Banda",
    "role": "vendor",                 // "vendor" | "admin"
    "nrc": "123456/78/1",             // required when the user row has an NRC
    "businessType": "Vegetables"      // optional (vendors)
  }
}
```

Response `200`:

```json
{
  "sessionId": "8f2a…",
  "chatToken": "eyJ…",                // signed, 24 h TTL, scope "chatbot"
  "identity": { "kind": "verified", "role": "vendor", "displayName": "Mary Banda" },
  "greeting": "Hello Mary Banda …",
  "suggestedPrompts": ["What is the status of my stand application?", "…"]
}
```

Errors: `401 identity_invalid`, `429 rate_limited`, `400 invalid_request`.

### 4.3 `POST /sessions/{sessionId}/messages` — send a message

Auth: `Authorization: Bearer <chatToken>` from §4.2.

Request: `{ "content": "What is my application status?" }` (1–2000 chars).

Response `200` — one assistant turn (after any internal tool round-trips):

```json
{
  "userMessage":  { "id": "u1", "role": "user", "content": "…", "createdAt": "…" },
  "assistantMessage": {
    "id": "a1",
    "role": "assistant",
    "content": "Your application **APP-1042** …",
    "createdAt": "…",
    "meta": {
      "verified": true,
      "toolsUsed": ["get_my_application_status"],
      "degraded": false
    }
  },
  "suggestedPrompts": ["…", "…"]
}
```

`meta.verified` — the reply is backed by database records read during this turn.
`meta.toolsUsed` — tool names executed (see §6). `meta.degraded` — the LLM could not
complete and a safe fallback string was returned instead.

Errors: `401 chat_token_invalid`, `404 session_not_found`, `429 rate_limited`,
`413 message_too_long`.

### 4.4 `GET /sessions/{sessionId}/messages` — conversation history

Auth: same Bearer token. Returns the **transcript** — `user` + `assistant`
messages in chronological order (max 200). Internal tool round-trips are not
exposed; they remain in the chatbot audit store. Only the session owner's token
can read it.

### 4.5 `POST /sessions/{sessionId}/close`

Auth: same Bearer token. Marks the session closed (further messages rejected with
`409 session_closed`). Optional UI nicety.

---

## 5. Rate limits (server-enforced, in-process sliding window)

| Endpoint | Limit | Key |
| --- | --- | --- |
| `POST /sessions` | 10 / hour per IP | remote_addr |
| `POST /sessions` | 30 / hour per identity phone | user.phone |
| messages | 30 / minute per session | session_id |

Responses use `429 rate_limited` with `retryAfterSeconds`.

---

## 6. Tool catalog (structured function calling)

The LLM receives these as OpenAI-compatible `tools` (`type: "function"`, JSON Schema
parameters). The service executes them **only** after binding to the session identity.

### Available to everyone (guests included)

| Tool | Purpose |
| --- | --- |
| `get_market_overview` | Open/closed counts, stands by zone and status, queue length |
| `explain_market_policy` | Grounded explanations — `topic`: `allocation` \| `payments` \| `permits` \| `verification` \| `reports` |

### Vendor-only (own data; scoping from server-side identity)

| Tool | Returns |
| --- | --- |
| `get_my_application_status` | Own application: status, queue position, business type, preferred zone, applied date, allocated stand (if any) |
| `get_my_payments` | Own payment records: amount, status, method, receipt number |
| `get_my_notifications` | Own notifications: unread count + latest 10 (type/title/message/date) |
| `get_my_financials` | Own daily-sales totals (incl. unpaid tax), latest tax payment, village-banking savings balance vs goal |

### Admin-only

| Tool | Returns |
| --- | --- |
| `get_application_statistics` | Totals by status, business-type mix, queue depth, stand occupancy |
| `get_queue_summary` | Pending applications in queue order (name, business type, preferred zone, position) |
| `list_recent_allocations` | Latest allocations from the audit log (stand, vendor, when, by whom, status) |
| `list_pending_verifications` | Payments awaiting confirmation with age; unresolved corruption reports |
| `find_suspicious_activity` | Deterministic rule-based flags: duplicate phones/names, paper-occupied stands (allocated >30 d without confirmed payment), stale pending payments (>72 h), ghost allocations (occupied stand with no matching vendor/payment record) |

**Denial contract.** When a role lacks a tool, execution returns
`{"ok": false, "denied": true, "error": "This information is only available to <role> accounts."}`
into the LLM context — the assistant then explains the boundary politely. No exception
leaks, no data leaks.

**Amounts.** All monetary values are returned as *formatted strings* (e.g.
`"ZMW 350.00"`); no floating-point arithmetic happens in the chatbot.

---

## 7. Verified/explained semantics (per message)

| Scenario | `meta.verified` | Example |
| --- | --- | --- |
| Reply composed from ≥1 successful tool result | `true` | "Your application is pending at position 12…" |
| Pure explanation / policy / guidance | `false` | "Allocation runs in first-in-first-out order…" |
| Assistant refused an action | `false` | "I can't allocate stands…" |
| Fallback after LLM failure | `false` + `meta.degraded: true` | "I gathered records but couldn't finish the summary…" |

The widget renders a "✓ verified data" badge on assistant bubbles when
`meta.verified === true`, and a muted "general guidance" note otherwise.

---

## 8. Error model

Every error response: `{ "error": { "code": "…", "message": "…" } }`

Codes: `invalid_request`, `identity_invalid`, `chat_token_invalid`, `session_not_found`,
`session_closed`, `message_too_long`, `rate_limited`, `llm_unavailable`, `internal_error`.

`llm_unavailable` (HTTP 503) only occurs when the configured LLM provider cannot be
reached *and* the mock fallback is disabled. The widget maps every error to a friendly
message + Retry button.

---

## 9. Environment variables

| Variable | Default | Meaning |
| --- | --- | --- |
| `CHATBOT_DATABASE_URL` | SQLite file `prisma/dev.db` (same data as the app) | SQLAlchemy URL. Prisma `file:` URLs are translated. Neon: `postgresql+psycopg://…` |
| `CHATBOT_SECRET_KEY` | dev fallback + warning | HMAC secret for chat tokens and identity stamping |
| `CHATBOT_LLM_PROVIDER` | `mock` | `mock` \| `openai` \| `openrouter` \| `groq` \| `custom` |
| `CHATBOT_LLM_API_KEY` | — | Provider API key (never logged, never in responses) |
| `CHATBOT_LLM_MODEL` | provider default | e.g. `gpt-4o-mini` |
| `CHATBOT_LLM_BASE_URL` | provider default | For `custom` providers |
| `CHATBOT_CORS_ORIGINS` | `http://localhost:3000` | Comma-separated allowed widget origins |
| `FLASK_API_URL` (frontend env) | — | Next.js rewrites `/api/v1/*` to this when set |
| `NEXT_PUBLIC_API_URL` (frontend env) | same-origin | Direct Flask origin for the widget |

---

## 10. Frontend behaviour contract (widget)

- Floating round button, bottom-right (`24px` inset; `16px` on mobile), hidden while the
  panel is open. Expands to a panel 380×560 (desktop), full-bleed sheet (≤600px).
- Session is created lazily on first open; `{sessionId, chatToken}` persists in
  `sessionStorage` under `standproof_chat_v1` and the widget replays history on reload.
- Identity auto-derives from the app session user (`app_user` in storage): guests get a
  "Public mode — log in for personalised answers" hint; vendors/admins get a role strip.
- States implemented: connecting (typing dots), sending (optimistic user bubble + dots),
  error banner with retry, empty state with suggested prompts, verified badge.
- All API access goes through `src/lib/chatbot.ts` (single client, contract-typed).
- Ownership note: the **frontend lead** owns the widget's visual system; the
  **chatbot engineer** owns the API client (`src/lib/chatbot.ts`) and hook logic.

---

## 11. Local development (chatbot service)

```bash
cd backend
python -m venv .venv && .venv\Scripts\activate   # windows; source .venv/bin/activate on unix
pip install -r requirements.txt -r requirements-dev.txt
copy .env.example .env                           # fill values (mock LLM works with no keys)
python wsgi.py                                   # http://127.0.0.1:5000
# in another shell, from repo root:
npm run dev                                      # set FLASK_API_URL=http://127.0.0.1:5000 in .env.local
```

Tests: `cd backend && python -m pytest tests/chatbot -v`

---

## 12. Hardening roadmap (after the backend lead's foundations land)

1. **JWT identity source** — replace DB-triple verification with Flask JWT-Extended
   tokens issued by the central auth routes; keep `identity.py` as the single seam.
2. **Session ownership across devices** — issue refreshable chat tokens; currently 24 h.
3. **Persistent stores** — merge chat tables into the Alembic migration chain
   (`backend/migrations/`) created by the backend lead; today the chat service owns its
   own `chat_session`/`chat_message` tables and creates them idempotently.
4. **Rate limiting** — move to shared Redis-backed limiter used by the whole API.
5. **Chatbot audit** — mirror assistant turns into the central `AuditLog` once the
   backend lead sanctions chatbot writes to the audit trail.

## 13. Non-goals

- No write access of any kind (no applications, allocations, payments, permits, reports
  written by the assistant).
- No escrow/funds claims. The assistant only describes payment states from records.
- No multi-tenant analytics for vendors; only admins see market-wide figures.
- The assistant does not replace the whistleblower channel (/reports page) — it explains
  how to use it.
