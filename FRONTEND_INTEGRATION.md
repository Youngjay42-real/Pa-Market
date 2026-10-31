# StandProof frontend integration handoff

The redesigned frontend is at the repository root. It preserves Next.js 14, React 18, TypeScript, CSS Modules and the existing QR library. Its new service boundary is `src/lib/standproof/`; view models are in `src/types/standproof.ts`. No Flask, Prisma or existing Next.js API implementation is changed by this frontend service layer.

## Current integration status

The core authentication, allocation and payment Flask adapter contract is still pending. The redesigned operational screens use an explicitly labelled browser demonstration and do not call legacy database, authentication, payment or allocation implementations. The repository already contains the chatbot engineer’s `docs/CHATBOT_CONTRACT.md`; its frontend client, hook, widget, backend and existing Next.js proxy remain preserved.

With `NEXT_PUBLIC_API_URL` absent, the service is in `demo` mode. `NEXT_PUBLIC_DEMO_MODE=true` explicitly selects demonstration mode even if an API URL exists. With an API URL configured and no approved adapter, mode is `unconfigured`: screens show an integration error and empty live records. A failed or missing real API must never silently fall back to sample records. These are public Next.js build-time environment variables; set them before `npm run build`.

## Demonstration behavior

- The 120 stands, applicants, administrator and vendors are fictional fixtures. The four existing trade zones and stand position fields are retained; readable A–D section labels augment the original `ST-...` IDs.
- The initial vendor is Mary Banda. Her accepted A-14 offer awaits vendor and official handover confirmations. A payment preview becomes eligible only after both demonstration confirmations.
- Choosing a profile is **not authentication**. New demonstration profiles contain only a name, phone number and optional business type; passwords and access tokens are never saved. Switching back from the administrator profile resumes the most recently created vendor in that browser tab. Reset restores the original fixtures and profiles.
- Demonstration records persist under the isolated `standproof-demo-v1` browser key. The selected profile uses session storage. Legacy storage is neither read nor overwritten. If storage is blocked, the demonstration works in memory. Do not enter actual personal information or confidential reports in the demo.
- Applications, human review, offers, acceptance and the two handover confirmations update one shared demonstration snapshot. Frontend state checks only make the demo coherent; they are not a substitute for backend permissions, constraints or business rules.
- A payment preview can become `pending` but can **never** become `successful` through a browser action. No DevDraft request, transaction reference, receipt, escrow claim or money movement is fabricated. Repeated preview requests return the existing pending record.
- Demo report details remain in memory for the current page session. Only the generated reference, status and creation time persist; descriptions, locations and email contacts are omitted from persistent storage and from cross-tab updates. They are not delivered to council staff or an external authority. No guarantee of anonymous, encrypted or confidential reporting is made.

## Connecting Flask

`createApiClient()` in `src/lib/standproof/client.ts` provides a transport configured by `NEXT_PUBLIC_API_URL`. It supports JSON, request cancellation, timeout, typed errors, HTTP-only cookie sessions and an optional access-token callback. It accepts only paths in the `/api/v1/` namespace. It contains no hard-coded route map. An API URL can be an origin or include `/api/v1`.

The backend lead must approve endpoint paths, schemas, error formats and session/CSRF behavior first. Implement a `StandproofAdapter` against that approved contract, map wire records to the frontend view models, and call `configureStandproofAdapter(adapter)` once from the application provider. The adapter's `getSnapshot()` must load only records authorised for the current user. Do not send every vendor's personal information to a vendor browser and rely on UI filtering.

The adapter interface currently includes demo profile selection to keep preview controls separate from screens. The service boundary rejects `selectPersona`, `createDemoVendor` and `resetDemo` in live mode; a live adapter must use genuine authentication flows with the agreed backend contract. The frontend must hide demonstration controls in live mode. Registration and login request schemas are intentionally not guessed. Successful live logout clears all cached records immediately; failed snapshot refreshes clear stale records, and older refresh responses cannot overwrite newer ones.

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

`src/components/chatbot/AssistantSurface.tsx` selects the existing team-owned `ChatWidget` when `NEXT_PUBLIC_CHATBOT_ENABLED=true`; otherwise it renders the clearly labelled local demo guide. The existing `src/lib/chatbot.ts`, `src/lib/chatbotTypes.ts`, `src/hooks/useChatbot.ts`, widget and `next.config.mjs` Flask rewrite are retained. Configure the documented `FLASK_API_URL` same-origin proxy or `NEXT_PUBLIC_API_URL` origin. Chatbot request/response schemas follow `docs/CHATBOT_CONTRACT.md`, which this frontend change does not edit. Do not copy a browser demo persona into the live widget’s `app_user` identity source; personalised chat requires genuine backend authentication. No production chatbot call or backend test was run as part of this frontend-only commit.
