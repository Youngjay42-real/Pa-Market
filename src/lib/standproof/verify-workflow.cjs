/* Run: node src/lib/standproof/verify-workflow.cjs
 * Exercises the frontend boundary without backend/provider requests. */
const fs = require("node:fs");
const path = require("node:path");
const assert = require("node:assert/strict");
const ts = require("typescript");
const root = path.resolve(__dirname, "../../..");
function sourceLoader() {
  const cache = new Map();
  return function load(file) {
    const resolved = path.resolve(file.endsWith(".ts") ? file : `${file}.ts`);
    if (cache.has(resolved)) return cache.get(resolved).exports;
    const compiledModule = { exports: {} }; cache.set(resolved, compiledModule);
    const code = ts.transpileModule(fs.readFileSync(resolved, "utf8"), { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 } }).outputText;
    const localRequire = name => name.startsWith(".") ? load(path.resolve(path.dirname(resolved), name)) : name.startsWith("@/") ? load(path.resolve(root, "src", name.slice(2))) : require(name);
    new Function("require", "module", "exports", code)(localRequire, compiledModule, compiledModule.exports);
    return compiledModule.exports;
  };
}
function storage() { const data = new Map(); return { getItem: key => data.get(key) || null, setItem: (key, value) => data.set(key, value), removeItem: key => data.delete(key), data }; }
function browser() { return { localStorage: storage(), sessionStorage: storage(), addEventListener: () => {} }; }
function deferred() { let resolve; const promise = new Promise(yes => { resolve = yes; }); return { promise, resolve }; }
async function verify() {
  global.window = browser();
  const load = sourceLoader();
  const { demoActions: actions, getDemoSnapshot: snapshot, hydrateDemo } = load(path.join(__dirname, "demo.ts"));
  hydrateDemo();
  assert.equal(snapshot().stands.length, 120);
  assert.equal(new Set(snapshot().stands.map(stand => stand.label)).size, 120);
  await assert.rejects(actions.confirmHandover("ALC-2026-0086", "vendor"));
  await actions.selectPersona("vendor");
  await assert.rejects(actions.initiatePayment("ALC-2026-0086"));
  await actions.confirmHandover("ALC-2026-0086", "vendor");
  assert.equal(snapshot().payments[0].status, "not_eligible");
  await assert.rejects(actions.confirmHandover("ALC-2026-0086", "official"));
  await actions.selectPersona("admin");
  await actions.confirmHandover("ALC-2026-0086", "official");
  assert.equal(snapshot().payments[0].status, "eligible");
  await actions.selectPersona("vendor");
  const pending = await actions.initiatePayment("ALC-2026-0086");
  assert.equal(pending.status, "pending");
  assert.equal(pending.providerReference, undefined);
  assert.equal(pending.receiptReference, undefined);
  assert.equal((await actions.initiatePayment("ALC-2026-0086")).id, pending.id);
  assert.equal(snapshot().payments.filter(record => record.allocationId === "ALC-2026-0086").length, 1);
  assert.equal(snapshot().payments.some(record => record.status === "successful"), false);
  const vendor = await actions.createDemoVendor({ fullName: "Workflow Test Vendor", phone: "+260977123456", businessType: "Textiles" });
  const stand = snapshot().stands.find(record => record.zone === "Textiles" && record.status === "available");
  const input = { businessType: "Textiles", phone: vendor.phone, preferredZone: "Textiles", preferredStandId: stand.id, description: "Handmade textiles and tailoring supplies." };
  const application = await actions.submitApplication(input);
  await assert.rejects(actions.submitApplication(input));
  await actions.selectPersona("admin");
  await actions.reviewApplication(application.id, "approved");
  const allocation = await actions.allocate(application.id, stand.id);
  await assert.rejects(actions.allocate(application.id, stand.id));
  await actions.selectPersona("vendor");
  assert.equal(snapshot().session.id, vendor.id);
  await assert.rejects(actions.acceptOffer("ALC-2026-0086"));
  await actions.acceptOffer(allocation.id);
  await actions.confirmHandover(allocation.id, "vendor");
  await actions.selectPersona("admin");
  await actions.confirmHandover(allocation.id, "official");
  await actions.selectPersona("vendor");
  assert.equal((await actions.initiatePayment(allocation.id)).status, "pending");
  const report = await actions.submitReport({ category: "Allocation concern", description: "PRIVATE_REPORT_BODY is fictional data for this workflow check.", location: "PRIVATE_LOCATION", contactEmail: "private-contact@example.test" });
  assert.equal(report.status, "received");
  await actions.markAllNotificationsRead();
  assert.equal(snapshot().notifications.some(record => record.vendorId === vendor.id && !record.read), false);
  const persisted = [...window.localStorage.data.values(), ...window.sessionStorage.data.values()].join("");
  for (const text of ["password", "PRIVATE_REPORT_BODY", "PRIVATE_LOCATION", "private-contact@example.test"]) assert.equal(persisted.includes(text), false, `${text} must not be persisted`);
  const restored = sourceLoader()(path.join(__dirname, "demo.ts")); restored.hydrateDemo();
  assert.equal(restored.getDemoSnapshot().allocations.some(record => record.id === allocation.id), true);
  assert.equal(restored.getDemoSnapshot().reports[0].id, report.id);
  assert.equal(restored.getDemoSnapshot().reports[0].description, "");
  assert.equal(restored.getDemoSnapshot().reports[0].contactEmail, undefined);
  await actions.resetDemo(); assert.equal(snapshot().applications.length, 7); assert.equal(snapshot().session.id, "VND-001");
  const { createApiClient, ApiError } = load(path.join(__dirname, "client.ts"));
  let request;
  global.fetch = async (url, init) => { request = { url: String(url), init }; return new Response(JSON.stringify({ ok: true }), { status: 200, headers: { "Content-Type": "application/json" } }); };
  assert.deepEqual(await createApiClient({ baseUrl: "https://example.test/api/v1" }).request("/stands"), { ok: true });
  assert.equal(request.url, "https://example.test/api/v1/stands"); assert.equal(request.init.credentials, "include");
  await assert.rejects(createApiClient({ baseUrl: "https://example.test" }).request("/legacy"), error => error instanceof ApiError && error.code === "INVALID_API_NAMESPACE");
  await assert.rejects(createApiClient({ baseUrl: "https://example.test" }).request("//attacker.test/api/v1/stands"));
  global.fetch = async () => new Response(JSON.stringify({ message: "Permission denied" }), { status: 403, headers: { "Content-Type": "application/json" } });
  await assert.rejects(createApiClient({ baseUrl: "https://example.test" }).request("/api/v1/stands"), error => error.status === 403 && error.message === "Permission denied");
  process.env.NEXT_PUBLIC_API_URL = "https://configured.example.test"; delete process.env.NEXT_PUBLIC_DEMO_MODE;
  const live = sourceLoader()(path.join(__dirname, "index.ts")); await live.refreshStandproof();
  assert.equal(live.getSnapshot().stands.length, 0, "Configured-but-unconnected mode cannot fall back to demo");
  await assert.rejects(live.submitReport({ category: "test", description: "No approved live contract exists." }));
  const liveSnapshot = { ...snapshot(), session: { id: "LIVE-TEST", role: "vendor", fullName: "Live adapter test", phone: "+260977123456" } };
  const adapter = { getSnapshot: async () => liveSnapshot, logout: async () => {} };
  await live.configureStandproofAdapter(adapter);
  await assert.rejects(live.selectPersona("admin")); await assert.rejects(live.resetDemo());
  const first = deferred(); const second = deferred(); let call = 0;
  adapter.getSnapshot = () => (++call === 1 ? first.promise : second.promise);
  const earlierRefresh = live.refreshStandproof(); const newerRefresh = live.refreshStandproof();
  second.resolve({ ...liveSnapshot, session: { ...liveSnapshot.session, fullName: "Newer authorised response" } }); await newerRefresh;
  first.resolve({ ...liveSnapshot, session: { ...liveSnapshot.session, fullName: "Stale response" } }); await earlierRefresh;
  assert.equal(live.getSnapshot().session.fullName, "Newer authorised response");
  adapter.getSnapshot = async () => { throw new Error("Session expired"); }; await live.refreshStandproof();
  assert.equal(live.getSnapshot().session, null); assert.equal(live.getSnapshot().applications.length, 0);
  adapter.getSnapshot = async () => liveSnapshot; await live.refreshStandproof(); await live.logout();
  assert.equal(live.getSnapshot().session, null); assert.equal(live.getSnapshot().payments.length, 0);
  console.log("PASS: full vendor/admin application-to-handover workflow; ownership; duplicate prevention; pending-only payments; persistence/report-data minimisation; notifications/reset; API transport/errors; configured-mode isolation; stale-response protection; logout/session-expiry cache clearing.");
}
const originalFetch = global.fetch; const originalWindow = global.window;
const originalApiUrl = process.env.NEXT_PUBLIC_API_URL; const originalDemoMode = process.env.NEXT_PUBLIC_DEMO_MODE;
verify().catch(error => { console.error(error); process.exitCode = 1; }).finally(() => {
  global.fetch = originalFetch; global.window = originalWindow;
  if (originalApiUrl === undefined) delete process.env.NEXT_PUBLIC_API_URL; else process.env.NEXT_PUBLIC_API_URL = originalApiUrl;
  if (originalDemoMode === undefined) delete process.env.NEXT_PUBLIC_DEMO_MODE; else process.env.NEXT_PUBLIC_DEMO_MODE = originalDemoMode;
});
