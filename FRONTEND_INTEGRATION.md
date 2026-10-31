# Pa Market frontend integration handoff

The redesigned frontend is at the repository root. It preserves Next.js 14, React 18, TypeScript, CSS Modules and the existing QR library. Its service boundary is `src/lib/standproof/`; view models are in `src/types/standproof.ts`.

## Current integration status

The approved Flask adapter is implemented in `src/lib/standproof/flask.ts` and installed by the application shell when the backend URL is configured. It loads market stands publicly and fetches account-specific records after real sign-in. The chatbot continues to use its separate approved contract in `docs/CHATBOT_CONTRACT.md`.

With `NEXT_PUBLIC_API_URL` absent, the service is in `demo` mode. `NEXT_PUBLIC_DEMO_MODE=true` explicitly selects demonstration mode even if an API URL exists. The API URL can be the Flask origin, its `/api/v1` base, or `/api/v1` to use the same-origin Next.js rewrite. All adapter requests use the approved `/api/v1` namespace. Backend failures show an error and empty live records rather than falling back to sample data. `NEXT_PUBLIC_*` variables are embedded when Next.js starts or builds, so redeploy the frontend after changing them.

## Demonstration behavior

- The 120 stands, applicants, administrator and vendors are fictional fixtures. The four existing trade zones and stand position fields are retained; readable A–D section labels augment the original `ST-...` IDs.
- The initial vendor is Mary Banda. Her accepted A-14 offer awaits vendor and official handover confirmations. A payment preview becomes eligible only after both demonstration confirmations.
- Choosing a profile is **not authentication**. New demonstration profiles contain only a name, phone number and optional business type; passwords and access tokens are never saved. Switching back from the administrator profile resumes the most recently created vendor in that browser tab. Reset restores the original fixtures and profiles.
- Demonstration records persist under the isolated `standproof-demo-v1` browser key. The selected profile uses session storage. Legacy storage is neither read nor overwritten. If storage is blocked, the demonstration works in memory. Do not enter actual personal information or confidential reports in the demo.
- Applications, human review, offers, acceptance and the two handover confirmations update one shared demonstration snapshot. Frontend state checks only make the demo coherent; they are not a substitute for backend permissions, constraints or business rules.
- A payment preview can become `pending` but can **never** become `successful` through a browser action. No DevDraft request, transaction reference, receipt, escrow claim or money movement is fabricated. Repeated preview requests return the existing pending record.
- Demo report details remain in memory for the current page session. Only the generated reference, status and creation time persist; descriptions, locations and email contacts are omitted from persistent storage and from cross-tab updates. They are not delivered to council staff or an external authority. No guarantee of anonymous, encrypted or confidential reporting is made.

## Connecting Flask

`createApiClient()` in `src/lib/standproof/client.ts` provides a transport configured by `NEXT_PUBLIC_API_URL`. It supports JSON, request cancellation, timeout, typed errors, HTTP-only cookie sessions and an optional access-token callback. An origin-only URL is normalized to `/api/v1`; an already versioned URL is preserved. `/api/v1` uses the same-origin proxy. Other URL path prefixes are rejected.

The installed `StandproofAdapter` maps the approved auth, stands, applications, allocations, payments, notifications, audit and reports endpoints to the frontend view models. Its `getSnapshot()` uses backend role-scoped list endpoints; vendor personal records are not obtained from admin-wide endpoints. Live mode disables demo persona and reset actions.

The adapter interface includes demo profile actions for preview mode, but the service boundary rejects `selectPersona`, `createDemoVendor` and `resetDemo` in live mode. Registration and login use the approved Flask auth routes from the auth screens. Successful live logout clears all cached records immediately; failed snapshot refreshes clear stale records, and older refresh responses cannot overwrite newer ones.

Required backend capabilities, **not new agreed endpoints**:

| Capability | Required behavior / fields |
| --- | --- |
| Authentication | Registration, login, logout, current user, roles; password policy and recovery if supported; backend-enforced permissions and session expiry |
| Stands | List/detail/filter; stand ID, spatial position, zone, category, status, area and fees represented as decimal strings |
| Applications | Submit/own records/admin review; stable references, queue order, decision reason, authorisation, duplicate prevention |
| Allocations | Explicit human offer, vendor acceptance, separate vendor/official handover records, verification and concurrent stand-conflict handling |
| Payments | Backend-derived eligibility and amount/currency, idempotent initiation, provider status polling or verified updates, pending/success/failed/refunded states, backend-produced receipt and reference |
| Notifications | Role-scoped list and persistent read/unread updates |
| Audit | Authorised, chronological actor/action/record/time/detail list; backend integrity protection |
| Reporting | Validated submission, attachment requirements if supported, protected contact information, real reference and delivery feedback |
| Chatbot | Agreed session/message/history/error schemas with role-scoped structured-tool service; responses must identify retrieved data versus generated explanations |

Backend enforcement is required for all payment conditions, idempotency, webhook authenticity, USD $5 transaction / $50 team limits and any hackathon refund deadline. The frontend does not implement or claim these server guarantees. Payment amount and fee strings in demo fixtures are presentation examples, not exchange rates or live charge instructions.

## Frontend workflow verification

Run `node src/lib/standproof/verify-workflow.cjs` from the project directory. This uses the installed TypeScript compiler to exercise the source directly in an isolated in-memory browser store. It checks the cross-role application/offer/handover journey, pending-only and repeated payment requests, role ownership, reload persistence, report-data minimisation, configured-mode isolation, API transport errors, stale responses and logout/session-expiry cache clearing. It makes no backend or payment-provider calls. Browser and production build checks remain separate acceptance steps.

## Existing code and ownership

The frontend-only commit omits the legacy Next.js API routes, Prisma schema, generated database client, payment helpers and old local application store. They are not the redesigned frontend’s service source. Existing remote backend and chatbot contract files are unchanged. No production keys, credentials, endpoints or webhook formats have been invented. Backend-owned `docs/API_CONTRACT.md`, `docs/PAYMENT_FLOW.md`, database documentation and Render configuration remain the respective owner's responsibility.

## Existing chatbot integration

`src/components/chatbot/AssistantSurface.tsx` selects the Flask-backed `ChatWidget` when `NEXT_PUBLIC_CHATBOT_ENABLED=true` or `NEXT_PUBLIC_API_URL` is configured, unless demo mode is explicit or the chatbot is explicitly disabled. Otherwise it renders the clearly labelled local guide. `FLASK_API_URL` is the Flask origin used by the Next.js same-origin proxy; setting `NEXT_PUBLIC_API_URL=/api/v1` routes both the widget and workspace API through it. Locally, `backend/wsgi.py` loads only `backend/.env`, so put `CHATBOT_LLM_PROVIDER=nvidia_nim` and the secret `CHATBOT_LLM_API_KEY` there, then restart Flask. Never put the key in a `NEXT_PUBLIC_*` variable. Personalised chat requires real backend authentication; browser demo personas are not sent as verified identities.
