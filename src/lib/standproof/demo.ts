import type { Allocation, ApplicationInput, AuditEvent, DemoSession, NotificationRecord, PaymentRecord, ReportInput, ReportRecord, StandApplication, StandproofSnapshot, UserRole } from "@/types/standproof";
import { createDemoSnapshot, DEMO_ADMIN, DEMO_VENDOR, ZONES } from "./fixtures";

const DATA_KEY = "standproof-demo-v1";
const SESSION_KEY = "standproof-demo-session-v1";
const VENDOR_PROFILE_KEY = "standproof-demo-vendor-profile-v1";
const VERSION = 1;
let current = createDemoSnapshot();
let hydrated = false;
let vendorProfile = { ...DEMO_VENDOR };
const listeners = new Set<() => void>();

function id(prefix: string) {
  const value = typeof crypto !== "undefined" && "randomUUID" in crypto ? crypto.randomUUID().slice(0, 8) : `${Date.now()}-${Math.random().toString(16).slice(2, 8)}`;
  return `${prefix}-${value.toUpperCase()}`;
}
function now() { return new Date().toISOString(); }
function notify() { listeners.forEach((listener) => listener()); }
function validSession(value: unknown): value is DemoSession {
  if (!value || typeof value !== "object") return false;
  const session = value as Partial<DemoSession>;
  return typeof session.id === "string" && typeof session.fullName === "string" && typeof session.phone === "string" && (session.role === "vendor" || session.role === "admin");
}
function hasStrings(value: unknown, keys: string[]) {
  return !!value && typeof value === "object" && keys.every((key) => typeof (value as Record<string, unknown>)[key] === "string");
}
function validSnapshot(value: unknown): value is Omit<StandproofSnapshot, "session"> {
  if (!value || typeof value !== "object") return false;
  const data = value as Partial<StandproofSnapshot>;
  if (!Array.isArray(data.stands) || data.stands.length !== 120 || !data.stands.every((stand) => hasStrings(stand, ["id", "label", "zone", "section", "category", "status", "monthlyFee", "currency"]) && ZONES.includes(stand.zone) && Number.isFinite(stand.row) && Number.isFinite(stand.col) && Number.isFinite(stand.area))) return false;
  return Array.isArray(data.applications) && data.applications.every((entry) => hasStrings(entry, ["id", "vendorId", "vendorName", "businessType", "phone", "preferredZone", "description", "status", "submittedAt"]) && Number.isFinite(entry.queuePosition))
    && Array.isArray(data.allocations) && data.allocations.every((entry) => hasStrings(entry, ["id", "applicationId", "vendorId", "vendorName", "standId", "offeredAt", "status"]))
    && Array.isArray(data.payments) && data.payments.every((entry) => hasStrings(entry, ["id", "allocationId", "vendorId", "amount", "currency", "status", "createdAt"]) && /^\d+\.\d{2}$/.test(entry.amount))
    && Array.isArray(data.notifications) && data.notifications.every((entry) => hasStrings(entry, ["id", "vendorId", "title", "message", "category", "createdAt", "href"]) && typeof entry.read === "boolean")
    && Array.isArray(data.audit) && data.audit.every((entry) => hasStrings(entry, ["id", "action", "actor", "entityType", "entityId", "details", "timestamp"]))
    && Array.isArray(data.reports) && data.reports.every((entry) => hasStrings(entry, ["id", "category", "description", "status", "createdAt"]));
}
function reportReferences(reports: ReportRecord[]): ReportRecord[] {
  // A reload can recover a demonstration reference without retaining report details or contact data.
  return reports.map((entry) => ({ id: entry.id, category: "Demo report", description: "", status: "received", createdAt: entry.createdAt }));
}
function save() {
  if (typeof window === "undefined") return;
  try {
    const { session, ...data } = current;
    window.localStorage.setItem(DATA_KEY, JSON.stringify({ version: VERSION, data: { ...data, reports: reportReferences(data.reports) } }));
    if (session) window.sessionStorage.setItem(SESSION_KEY, JSON.stringify(session));
    else window.sessionStorage.removeItem(SESSION_KEY);
    window.sessionStorage.setItem(VENDOR_PROFILE_KEY, JSON.stringify(vendorProfile));
  } catch { /* The demo remains usable in memory when browser storage is unavailable. */ }
}
function commit(next: StandproofSnapshot) { current = next; save(); notify(); }
function actor(role?: UserRole) {
  const user = current.session;
  if (!user) throw new Error("Choose a demonstration profile to continue.");
  if (role && user.role !== role) throw new Error(`Switch to the ${role} demonstration profile for this action.`);
  return user;
}
function allocation(id: string) {
  const value = current.allocations.find((item) => item.id === id);
  if (!value) throw new Error("This allocation could not be found.");
  return value;
}
function appendAudit(action: string, entityType: string, entityId: string, details: string): AuditEvent[] {
  return [{ id: id("AUD-DEMO"), action, actor: current.session?.fullName || "Demo reporter", entityType, entityId, details, timestamp: now() }, ...current.audit];
}
function notification(vendorId: string, title: string, message: string, category: NotificationRecord["category"], href = "/vendor/dashboard"): NotificationRecord {
  return { id: id("NTF-DEMO"), vendorId, title, message, category, read: false, createdAt: now(), href };
}

export function subscribeDemo(listener: () => void) {
  listeners.add(listener);
  return () => { listeners.delete(listener); };
}
export function getDemoSnapshot() { return current; }
export function hydrateDemo() {
  if (hydrated || typeof window === "undefined") return;
  hydrated = true;
  let next = createDemoSnapshot();
  try {
    const raw = window.localStorage.getItem(DATA_KEY);
    if (raw) {
      const saved = JSON.parse(raw);
      if (saved.version === VERSION && validSnapshot(saved.data)) next = { ...saved.data, reports: reportReferences(saved.data.reports), session: null };
    }
    const rawSession = window.sessionStorage.getItem(SESSION_KEY);
    const rawVendorProfile = window.sessionStorage.getItem(VENDOR_PROFILE_KEY);
    if (rawVendorProfile) {
      const profile = JSON.parse(rawVendorProfile);
      if (validSession(profile) && profile.role === "vendor") vendorProfile = profile;
    }
    if (rawSession) {
      const session = JSON.parse(rawSession);
      if (validSession(session)) next = { ...next, session };
    }
  } catch { /* A corrupt or blocked browser store starts a fresh demo. */ }
  current = next;
  window.addEventListener("storage", (event) => {
    if (event.key !== DATA_KEY || !event.newValue) return;
    try {
      const saved = JSON.parse(event.newValue);
      if (saved.version === VERSION && validSnapshot(saved.data)) {
        current = { ...saved.data, reports: reportReferences(saved.data.reports), session: current.session };
        notify();
      }
    } catch { /* Ignore malformed state from another tab. */ }
  });
  notify();
}

export const demoActions = {
  async selectPersona(role: UserRole) {
    const session = { ...(role === "admin" ? DEMO_ADMIN : vendorProfile) };
    commit({ ...current, session });
    return session;
  },
  async createDemoVendor(input: { fullName: string; phone: string; businessType?: string }) {
    if (input.fullName.trim().length < 2 || input.phone.replace(/\D/g, "").length < 9) throw new Error("Enter your name and a valid phone number.");
    const session: DemoSession = { id: id("VND-DEMO"), fullName: input.fullName.trim(), phone: input.phone.trim(), businessType: input.businessType?.trim(), role: "vendor" };
    vendorProfile = session;
    commit({ ...current, session });
    return session;
  },
  async logout() { commit({ ...current, session: null }); },
  async submitApplication(input: ApplicationInput) {
    const user = actor("vendor");
    if (current.applications.some((item) => item.vendorId === user.id && item.status !== "rejected")) throw new Error("Your current application is already in progress. View it in your dashboard.");
    if (!input.businessType.trim() || !ZONES.includes(input.preferredZone) || input.description.trim().length < 10 || input.phone.replace(/\D/g, "").length < 9) throw new Error("Complete your business details, phone number and a description of at least 10 characters.");
    if (input.preferredStandId) {
      const stand = current.stands.find((item) => item.id === input.preferredStandId);
      if (!stand || stand.status !== "available") throw new Error("Your preferred stand is no longer available. Please choose another stand.");
      if (stand.zone !== input.preferredZone) throw new Error("Choose a stand in your preferred zone.");
    }
    const item: StandApplication = { ...input, businessType: input.businessType.trim(), description: input.description.trim(), phone: input.phone.trim(), id: id("APP-DEMO"), vendorId: user.id, vendorName: user.fullName, status: "pending", queuePosition: Math.max(0, ...current.applications.map((entry) => entry.queuePosition)) + 1, submittedAt: now() };
    commit({ ...current, applications: [...current.applications, item], notifications: [notification(user.id, "Application received", `Your demonstration application ${item.id} is awaiting review.`, "application"), ...current.notifications], audit: appendAudit("Application received", "application", item.id, "Demonstration application added to the review queue.") });
    return item;
  },
  async reviewApplication(applicationId: string, decision: "approved" | "rejected", note?: string) {
    actor("admin");
    const item = current.applications.find((entry) => entry.id === applicationId);
    if (!item) throw new Error("Application not found.");
    if (item.status !== "pending") throw new Error("This application has already been reviewed.");
    if (decision === "rejected" && !note?.trim()) throw new Error("Give a reason so the vendor understands the decision.");
    const updated: StandApplication = { ...item, status: decision, reviewNote: note?.trim() };
    commit({ ...current, applications: current.applications.map((entry) => entry.id === item.id ? updated : entry), notifications: [notification(item.vendorId, `Application ${decision}`, decision === "approved" ? "Your demonstration application was reviewed and approved. A stand offer is the next step." : `Your demonstration application was declined. ${note?.trim()}`, "application"), ...current.notifications], audit: appendAudit(`Application ${decision}`, "application", item.id, note?.trim() || "Application reviewed by a demonstration administrator.") });
    return updated;
  },
  async allocate(applicationId: string, standId: string) {
    actor("admin");
    const item = current.applications.find((entry) => entry.id === applicationId);
    const stand = current.stands.find((entry) => entry.id === standId);
    if (!item || item.status !== "approved") throw new Error("Review and approve the application before offering a stand.");
    if (!stand || stand.status !== "available") throw new Error("This stand is no longer available.");
    if (current.allocations.some((entry) => entry.applicationId === item.id)) throw new Error("This application already has a stand offer.");
    if (stand.zone !== item.preferredZone) throw new Error("Choose an available stand in the application's preferred zone.");
    const value: Allocation = { id: id("ALC-DEMO"), applicationId: item.id, vendorId: item.vendorId, vendorName: item.vendorName, standId, offeredAt: now(), status: "offered" };
    const payment: PaymentRecord = { id: id("PAY-DEMO"), allocationId: value.id, vendorId: item.vendorId, amount: "3.00", currency: "USD", status: "not_eligible", createdAt: now() };
    commit({ ...current, stands: current.stands.map((entry) => entry.id === standId ? { ...entry, status: "reserved", vendorId: item.vendorId, vendorName: item.vendorName } : entry), applications: current.applications.map((entry) => entry.id === item.id ? { ...entry, status: "allocated" } : entry), allocations: [value, ...current.allocations], payments: [payment, ...current.payments], notifications: [notification(item.vendorId, "A stand offer for you", `Your demonstration offer for stand ${stand.label} is ready to review.`, "allocation"), ...current.notifications], audit: appendAudit("Stand offered", "allocation", value.id, `${stand.label} offered to ${item.vendorName} after administrator review.`) });
    return value;
  },
  async acceptOffer(allocationId: string) {
    const user = actor("vendor");
    const item = allocation(allocationId);
    if (item.vendorId !== user.id) throw new Error("This offer belongs to another demonstration profile.");
    if (item.acceptedAt) return item;
    const updated: Allocation = { ...item, acceptedAt: now(), status: "accepted" };
    commit({ ...current, allocations: current.allocations.map((entry) => entry.id === item.id ? updated : entry), stands: current.stands.map((entry) => entry.id === item.standId ? { ...entry, status: "handover" } : entry), notifications: [notification(user.id, "Offer accepted", "Both you and an authorised official must confirm physical handover before payment eligibility.", "handover"), ...current.notifications], audit: appendAudit("Offer accepted", "allocation", item.id, "Vendor accepted the demonstration stand offer.") });
    return updated;
  },
  async confirmHandover(allocationId: string, role: "vendor" | "official") {
    const user = actor(role === "official" ? "admin" : "vendor");
    const item = allocation(allocationId);
    if (role === "vendor" && item.vendorId !== user.id) throw new Error("You may only confirm your own handover.");
    if (!item.acceptedAt) throw new Error("The vendor must accept the stand offer first.");
    if (role === "vendor" && item.vendorConfirmedAt || role === "official" && item.officialConfirmedAt) return item;
    const updated: Allocation = { ...item, ...(role === "vendor" ? { vendorConfirmedAt: now() } : { officialConfirmedAt: now() }), status: "handover" };
    const complete = !!updated.vendorConfirmedAt && !!updated.officialConfirmedAt;
    if (complete) { updated.status = "verified"; updated.verifiedAt = now(); }
    commit({ ...current, allocations: current.allocations.map((entry) => entry.id === item.id ? updated : entry), stands: current.stands.map((entry) => entry.id === item.standId ? { ...entry, status: complete ? "occupied" : "verification" } : entry), payments: current.payments.map((entry) => entry.allocationId === item.id && entry.status === "not_eligible" && complete ? { ...entry, status: "eligible" } : entry), notifications: [notification(item.vendorId, complete ? "Handover confirmations complete" : "Handover confirmation recorded", complete ? "Both demonstration confirmations are recorded. The payment preview is now eligible. No real money will move." : `The ${role === "official" ? "official" : "vendor"} demonstration confirmation is recorded. The other confirmation is still required.`, "handover", "/vendor/payment"), ...current.notifications], audit: appendAudit(role === "official" ? "Official handover confirmed" : "Vendor handover confirmed", "allocation", item.id, complete ? "Both demonstration confirmations recorded; payment preview eligible." : "One demonstration confirmation recorded; awaiting the other party.") });
    return updated;
  },
  async initiatePayment(allocationId: string) {
    const user = actor("vendor");
    const item = allocation(allocationId);
    if (item.vendorId !== user.id) throw new Error("You may only view your own payment preview.");
    const payment = current.payments.find((entry) => entry.allocationId === item.id);
    if (!payment) throw new Error("Payment record not found.");
    if (payment.status === "pending") return payment;
    if (!item.acceptedAt || !item.vendorConfirmedAt || !item.officialConfirmedAt || !item.verifiedAt || payment.status !== "eligible") throw new Error("Both handover confirmations are required before the payment preview can start.");
    // This demo deliberately cannot transition into a successful provider payment.
    const updated: PaymentRecord = { ...payment, status: "pending" };
    commit({ ...current, payments: current.payments.map((entry) => entry.id === payment.id ? updated : entry), notifications: [notification(user.id, "Payment preview pending", "No payment was processed. A real transaction requires the backend DevDraft adapter and server-side verification.", "payment", "/vendor/payment"), ...current.notifications], audit: appendAudit("Payment preview requested", "payment", payment.id, "Demonstration only. No provider request, funds movement, transaction reference or successful receipt.") });
    return updated;
  },
  async markNotificationRead(notificationId: string) {
    const user = actor();
    commit({ ...current, notifications: current.notifications.map((entry) => entry.id === notificationId && entry.vendorId === user.id ? { ...entry, read: true } : entry) });
  },
  async markAllNotificationsRead() {
    const user = actor();
    commit({ ...current, notifications: current.notifications.map((entry) => entry.vendorId === user.id ? { ...entry, read: true } : entry) });
  },
  async submitReport(input: ReportInput) {
    if (!input.category.trim() || input.description.trim().length < 20) throw new Error("Choose a category and provide at least 20 characters of detail.");
    if (input.contactEmail && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(input.contactEmail.trim())) throw new Error("Enter a valid email address or leave it blank.");
    const value: ReportRecord = { ...input, category: input.category.trim(), description: input.description.trim(), location: input.location?.trim(), contactEmail: input.contactEmail?.trim(), id: id("RPT-DEMO"), status: "received", createdAt: now() };
    commit({ ...current, reports: [value, ...current.reports], audit: appendAudit("Demo report recorded", "report", value.id, "A fictional report was saved in this browser only. No external authority was notified.") });
    return value;
  },
  async resetDemo() {
    vendorProfile = { ...DEMO_VENDOR };
    const session = current.session ? { ...(current.session.role === "admin" ? DEMO_ADMIN : DEMO_VENDOR) } : null;
    commit({ ...createDemoSnapshot(), session });
  },
};
