# Pa Market

A market allocation workspace for Lusaka City Market, built with Next.js 14, React 18, TypeScript and CSS Modules. Pa Market follows an application through review, a stand offer, acceptance, two-party handover and backend-controlled payment eligibility.

## Run locally

```bash
npm ci
npm run dev
```

Open the development URL printed by Next.js. To preview the production build:

```bash
npm run build
npm start
```

If port 3000 is occupied, use `npm start -- --port 3100`.

## Explore the demonstration

Choose **Sign in**, then **Open vendor demo** or **Open administrator demo**. Registration also offers **Start a new vendor demo** for an empty application journey. The workspace account menu switches between the administrator and the current demo vendor. Profile selection is not authentication.

The market explorer has 120 fictional stands in the existing Produce, Textiles, Hardware and Food Court zones. Search, category/zone/status filters, stand selection, zoom, allocation queue and stand details work. Administrative review and allocation require explicit confirmation. Vendor and official handover confirmations update the same sample records and audit trail.

The interactive **Market stand map** is available at `/map`. In the demonstration it shows fictional stands; on Render it displays backend inventory and remains empty until real stand records are added. Demo stands are not seeded into production.

**This is a labelled frontend demonstration.** It does not process DevDraft payments, authenticate real users, issue valid trading permits, deliver reports to officials or call an AI provider. A demo payment request stays pending; the browser never manufactures successful payment confirmation. Real API failures never silently become demonstration data.

## Render administrator

Before deploying, set `ADMIN_BOOTSTRAP_PASSWORD` to a strong private value in the `pamarket-backend` service's Render environment settings. The Blueprint provisions the initial administrator with phone number `0776596009`; sign in at `/login` using that phone number and the password you set. The password is never committed or printed by the bootstrap command. Keep all three `ADMIN_BOOTSTRAP_*` values configured together. Provisioning is idempotent and does not add demo vendors or stands.

## Routes

| Area | Routes |
| --- | --- |
| Public | `/`, `/map`, `/login`, `/vendor/register` |
| Vendor | `/vendor/dashboard`, `/vendor/apply`, `/vendor/payment`, `/vendor/permit` |
| Administration | `/admin`, `/admin/applications`, `/admin/allocate`, `/admin/verify`, `/admin/payments`, `/admin/audit-logs` |
| Updates and reporting | `/notifications`, `/whistleblower` |

`/dashboard` redirects to the vendor dashboard. Navigation adapts to mobile, tables scroll within their containers and the spatial map can pan within its own viewport.

## Integration and ownership

`src/lib/standproof/` isolates fixtures, persistent demo workflows and the typed Flask adapter. `src/types/standproof.ts` defines frontend view models. `NEXT_PUBLIC_API_URL` accepts the Flask origin, its `/api/v1` base, or `/api/v1` to use the same-origin proxy. The adapter keeps requests in the approved namespace and loads backend records when the app starts. Backend failures show an error and empty live records rather than sample data. `NEXT_PUBLIC_DEMO_MODE=true` explicitly selects demo mode.

The Market Assistant uses the Flask chatbot contract when `NEXT_PUBLIC_CHATBOT_ENABLED=true` or a backend URL is configured; set `NEXT_PUBLIC_CHATBOT_ENABLED=false` or `NEXT_PUBLIC_DEMO_MODE=true` to keep the local guide. `FLASK_API_URL` enables the same-origin proxy; set `NEXT_PUBLIC_API_URL=/api/v1` to use it for both frontend APIs and chat. An absolute `NEXT_PUBLIC_API_URL` calls Flask directly. Demo personas are never passed off as backend-authenticated identities. The adapter and its approved route mappings are documented in [the frontend integration handoff](FRONTEND_INTEGRATION.md).

This frontend commit excludes the legacy Next.js API routes, Prisma schema, generated database client, and database/payment helpers. The repository’s existing `backend/` and `docs/CHATBOT_CONTRACT.md` remain unchanged.

## Validation

```bash
npm run lint
npx tsc --noEmit --incremental false
node src/lib/standproof/verify-workflow.cjs
npm run build
```

The workflow verification uses isolated in-memory browser storage and makes no provider requests. It exercises cross-role review/allocation/handover, record ownership, duplicate prevention, pending-only payment previews, persistence, API errors, stale responses and logout cache clearing.

The frontend was verified on desktop, laptop, tablet and mobile, including the complete cross-role handover journey. Inter is served locally; no external font request is required to build or run the interface.
