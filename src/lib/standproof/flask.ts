"use client";

/**
 * Live Flask adapter for the PaMarket backend contract (docs/API_CONTRACT.md).
 *
 * Implements `StandproofAdapter` against the approved `/api/v1` endpoints
 * only — no invented routes, statuses or payment behaviour:
 *
 * - auth:        POST /auth/signup · /auth/login · GET /auth/me (JWT bearer)
 * - stands:      GET /stands (+ /stands/meta for zone categories)
 * - applications POST /applications · GET /applications{,/mine} · POST …/review
 * - allocations  POST /allocations · GET …{,/mine} · POST …/accept · POST …/handover
 * - payments     POST /payments/initiate (Idempotency-Key) · GET /history · GET …/status
 * - notifications GET /notifications · POST …/{id}/read
 * - audit        GET /audit-logs
 * - reports      POST /reports (pseudonymous — only the reference is kept)
 *
 * Server decisions are never simulated here: statuses pass through the wire
 * values, payments require the backend's own verification, and amounts come
 * from the database records.
 */

import type {
  Allocation,
  ApplicationInput,
  AuditEvent,
  DemoSession,
  MarketStand,
  MarketZone,
  NotificationRecord,
  PaymentRecord,
  ReportInput,
  ReportRecord,
  ReportStatus,
  StandApplication,
  StandproofAdapter,
  StandproofSnapshot,
} from "@/types/standproof";
import { ApiError, createApiClient } from "./client";

type Client = ReturnType<typeof createApiClient>;

const TOKEN_KEY = "standproof.jwt";

export function getAccessToken(): string | null {
  try {
    const value = window.localStorage.getItem(TOKEN_KEY);
    return value && /^[A-Za-z0-9\-_.]+$/.test(value) ? value : null;
  } catch {
    return null;
  }
}

function saveAccessToken(token: string | null) {
  try {
    if (token) window.localStorage.setItem(TOKEN_KEY, token);
    else window.localStorage.removeItem(TOKEN_KEY);
  } catch {
    /* Token stays in memory only when storage is unavailable. */
  }
}

/* ------------------------------------------------------------------ wire */

interface WireUser {
  id: string;
  phone: string;
  full_name: string;
  role: "vendor" | "admin";
  nrc?: string | null;
  business_type?: string | null;
}

interface WireAuth {
  token: string;
  user: WireUser;
}

interface WireMe extends WireUser {
  vendor_id: string | null;
  unread_notifications: number;
}

interface WireStands {
  stands: Array<{
    id: string;
    code: string;
    row: number;
    col: number;
    zone: string;
    status: string;
    vendor_name?: string | null;
    vendor_id?: string | null;
    fee_amount: string;
    currency: string;
  }>;
}

interface WireMeta {
  zones: string[];
  business_categories: string[];
  category_zones: Record<string, string[]>;
}

interface WireApplications {
  applications: Array<{
    id: string;
    vendor_id: string;
    status: string;
    queue_position: number;
    business_type: string;
    preferred_zone: string;
    notes: string | null;
    decision_reason: string | null;
    created_at: string;
    allocation_id?: string | null;
    vendor?: {
      id: string;
      full_name: string;
      phone: string;
      business_type: string | null;
    };
  }>;
}

interface WireAllocations {
  allocations: Array<{
    id: string;
    application_id: string;
    stand_id: string;
    vendor_id: string;
    status: string;
    offered_at: string;
    accepted_at: string | null;
    handover: {
      vendor: { confirmed_at: string; meeting_location: string | null } | null;
      official: { confirmed_at: string; meeting_location: string | null } | null;
    };
    stand?: { code: string; zone: string };
  }>;
}

interface WirePayments {
  payments: Array<{
    id: string;
    allocation_id: string;
    vendor_id: string;
    amount: string;
    currency: string;
    status: string;
    provider_reference: string | null;
    receipt_no: string | null;
    created_at: string;
  }>;
}

interface WireNotifications {
  notifications: Array<{
    id: string;
    type: string;
    title: string;
    message: string;
    read: boolean;
    created_at: string;
  }>;
}

interface WireAudit {
  logs: Array<{
    id: string;
    action: string;
    actor: string;
    actor_role: string | null;
    entity_type: string;
    entity_id: string;
    details: string | null;
    recorded_at: string;
  }>;
}

/* ------------------------------------------------------------- mapping */

const ZONES: MarketZone[] = ["Produce", "Textiles", "Hardware", "Food Court"];

const STAND_STATUS_BY_WIRE: Record<string, MarketStand["status"]> = {
  available: "available",
  reserved: "reserved",
  occupied: "occupied",
  maintenance: "suspended",
};

const APPLICATION_STATUS_BY_WIRE: Record<string, StandApplication["status"]> = {
  submitted: "pending",
  under_review: "pending",
  approved: "approved",
  rejected: "rejected",
  allocated: "allocated",
  cancelled: "cancelled",
};

const ALLOCATION_STATUS_BY_WIRE: Record<string, Allocation["status"]> = {
  offered: "offered",
  accepted: "accepted",
  handover_confirmed: "verified",
  completed: "verified",
  expired: "expired",
  cancelled: "cancelled",
};

const NOTIFICATION_CATEGORY_BY_WIRE: Record<string, NotificationRecord["category"]> = {
  application_received: "application",
  application_approved: "application",
  application_rejected: "application",
  allocation_offered: "allocation",
  allocation_accepted: "allocation",
  handover_confirmed: "handover",
  payment_successful: "payment",
  payment_failed: "payment",
  payment_refunded: "payment",
  report_received: "system",
};

const NOTIFICATION_HREF_BY_CATEGORY: Record<NotificationRecord["category"], string> = {
  application: "/vendor/dashboard",
  allocation: "/vendor/dashboard",
  handover: "/vendor/payment",
  payment: "/vendor/payment",
  system: "/notifications",
};

/** Grid section derived from the stand's column (deterministic presentation
 * grouping of the backend row/col layout; A–D like the market canvas). */
function sectionForCol(col: number): "A" | "B" | "C" | "D" {
  if (col < 0 || Number.isNaN(col)) return "A";
  return (["A", "B", "C", "D"] as const)[Math.min(3, Math.floor(col / 3))];
}

function zoneOf(zone: string): MarketZone {
  return (ZONES as string[]).includes(zone) ? (zone as MarketZone) : "Produce";
}

function standStateByWire(status: string): MarketStand["status"] {
  return STAND_STATUS_BY_WIRE[status] ?? "suspended";
}

function applicationStateByWire(status: string): StandApplication["status"] {
  return APPLICATION_STATUS_BY_WIRE[status] ?? "pending";
}

function allocationStateByWire(status: string): Allocation["status"] {
  return ALLOCATION_STATUS_BY_WIRE[status] ?? "expired";
}

function paymentRecord(wire: WirePayments["payments"][number], fallbackVendorId: string): PaymentRecord {
  const status = wire.status;
  const known: PaymentRecord["status"][] = ["pending", "successful", "failed", "refunded", "disputed"];
  return {
    id: wire.id,
    allocationId: wire.allocation_id,
    vendorId: wire.vendor_id || fallbackVendorId,
    amount: /^\d+\.\d{2}$/.test(wire.amount) ? wire.amount : "0.00",
    currency: wire.currency === "USD" ? "USD" : "ZMW",
    status: (known as string[]).includes(status) ? (status as PaymentRecord["status"]) : "pending",
    providerReference: wire.provider_reference ?? undefined,
    receiptReference: wire.receipt_no ?? undefined,
    createdAt: wire.created_at,
  };
}

/* ------------------------------------------------------------------ state */

interface SessionContext {
  user: WireMe;
  vendorId: string;
  fullName: string;
  phone: string;
}

export function createFlaskAdapter() {
  // Tolerant base: an env value without the /api/v1 suffix still lands on the
  // approved namespace (the render dashboard sometimes stores the bare host).
  const rawBase = process.env.NEXT_PUBLIC_API_URL ?? "";
  const normalizedBase = /^https?:\/\//i.test(rawBase.trim())
    ? rawBase.trim().replace(/\/$/, "").replace(/\/api\/v1$/, "") + "/api/v1"
    : rawBase;
  const api: Client = createApiClient({ baseUrl: normalizedBase, getAccessToken: getAccessToken });
  const paymentIdempotencyKeys = new Map<string, string>();
  const localReports: ReportRecord[] = [];
  let cachedStandCategory: (zone: string) => string = () => "Market stand";

  function sessionFromMe(me: WireMe): DemoSession {
    return {
      id: me.vendor_id ?? me.id,
      fullName: me.full_name,
      role: me.role,
      phone: me.phone,
      businessType: me.business_type ?? undefined,
    };
  }

  async function loadContext(): Promise<SessionContext | null> {
    if (!getAccessToken()) return null;
    try {
      const me = await api.request<WireMe>("/auth/me");
      return {
        user: me,
        vendorId: me.vendor_id ?? me.id,
        fullName: me.full_name,
        phone: me.phone,
      };
    } catch (error) {
      // Expired/invalid JWT: continue as a guest instead of pretending.
      if (error instanceof ApiError && (error.status === 401 || error.status === 422)) {
        saveAccessToken(null);
        return null;
      }
      throw error;
    }
  }

  async function applyStandCategories() {
    try {
      const meta = await api.request<WireMeta>("/stands/meta");
      const byZone: Record<string, string> = {};
      for (const [category, zones] of Object.entries(meta.category_zones)) {
        for (const zone of zones) if (!(zone in byZone)) byZone[zone] = category;
      }
      cachedStandCategory = (zone: string) => byZone[zone] ?? "Market stand";
    } catch {
      cachedStandCategory = () => "Market stand";
    }
  }

  function standToView(wire: WireStands["stands"][number]): MarketStand {
    const zone = zoneOf(wire.zone);
    return {
      id: wire.id,
      label: wire.code,
      row: Number.isFinite(wire.row) ? wire.row : 1,
      col: Number.isFinite(wire.col) ? wire.col : 1,
      zone,
      section: sectionForCol(wire.col),
      category: cachedStandCategory(wire.zone),
      status: standStateByWire(wire.status),
      area: 0, // the backend contract carries no area; the UI shows "not recorded"
      monthlyFee: /^\d+(\.\d{1,2})?$/.test(wire.fee_amount) ? wire.fee_amount : "0.00",
      currency: wire.currency === "USD" ? "USD" : (wire.currency as "ZMW"),
      vendorName: wire.vendor_name ?? undefined,
      vendorId: wire.vendor_id ?? undefined,
    };
  }

  function applicationToView(
    wire: WireApplications["applications"][number],
    context: SessionContext | null,
  ): StandApplication {
    const vendorName = wire.vendor?.full_name ?? context?.fullName ?? wire.vendor_id;
    const phone = wire.vendor?.phone ?? context?.phone ?? "";
    return {
      id: wire.id,
      vendorId: wire.vendor_id,
      vendorName,
      businessType: wire.business_type,
      phone,
      preferredZone: zoneOf(wire.preferred_zone),
      description: wire.notes ?? "",
      status: applicationStateByWire(wire.status),
      queuePosition: Number.isFinite(wire.queue_position) ? wire.queue_position : 0,
      submittedAt: wire.created_at,
      reviewNote: wire.decision_reason ?? undefined,
    };
  }

  function allocationToView(
    wire: WireAllocations["allocations"][number],
    vendorNameByIdAndApplication: Map<string, Map<string, string>>,
    fallbackVendorName: string | undefined,
  ): Allocation {
    const vendorName =
      vendorNameByIdAndApplication.get(wire.vendor_id)?.get(wire.application_id) ??
      fallbackVendorName ??
      wire.vendor_id;
    return {
      id: wire.id,
      applicationId: wire.application_id,
      vendorId: wire.vendor_id,
      vendorName,
      standId: wire.stand_id,
      offeredAt: wire.offered_at,
      acceptedAt: wire.accepted_at ?? undefined,
      vendorConfirmedAt: wire.handover?.vendor?.confirmed_at ?? undefined,
      officialConfirmedAt: wire.handover?.official?.confirmed_at ?? undefined,
      verifiedAt:
        wire.status === "handover_confirmed" || wire.status === "completed"
          ? wire.handover?.official?.confirmed_at ?? wire.handover?.vendor?.confirmed_at ?? undefined
          : undefined,
      status: allocationStateByWire(wire.status),
    };
  }

  /** Advisory: why is this allocation's payment blocked right now? */
  async function attachEligibility(
    allocations: Allocation[],
    vendorId: string,
  ): Promise<void> {
    const candidates = allocations
      .filter(a => a.vendorId === vendorId)
      .slice(0, 2);
    await Promise.all(
      candidates.map(async allocation => {
        const verdict = await api.request<{ eligible?: boolean; reasons?: string[] }>(
          `/allocations/${encodeURIComponent(allocation.id)}/eligibility`,
        );
        allocation.eligible = Boolean(verdict.eligible);
        allocation.eligibilityReasons = Array.isArray(verdict.reasons) ? verdict.reasons : [];
      }),
    );
  }

  function notificationToView(
    wire: WireNotifications["notifications"][number],
    vendorId: string,
  ): NotificationRecord {
    const category = NOTIFICATION_CATEGORY_BY_WIRE[wire.type] ?? "system";
    return {
      id: wire.id,
      vendorId,
      title: wire.title,
      message: wire.message,
      category,
      read: Boolean(wire.read),
      createdAt: wire.created_at,
      href: NOTIFICATION_HREF_BY_CATEGORY[category],
    };
  }

  function auditToView(
    wire: WireAudit["logs"][number],
    context: SessionContext | null,
  ): AuditEvent {
    // The wire carries the acting account id; present it without claiming a
    // person we cannot resolve — role + id slice act as the attribution.
    const isOwn = context ? wire.actor === context.user.id : false;
    const role = wire.actor_role ?? "";
    const actor = wire.actor
      ? isOwn
        ? "You"
        : role
          ? `${role} · ${wire.actor.slice(0, 8)}`
          : wire.actor.slice(0, 12)
      : "system";
    return {
      id: wire.id,
      action: wire.action,
      actor,
      entityType: wire.entity_type,
      entityId: wire.entity_id,
      details: wire.details ?? "",
      timestamp: wire.recorded_at,
    };
  }

  function reportRecord(input: ReportInput, reference: string): ReportRecord {
    // Only the pseudonymous reference is retained; the payload itself is not
    // re-shown because the backend cannot verify stored report content.
    return {
      id: reference || input.category,
      category: input.category,
      description: "", // description deliberately not localised as a record
      location: undefined,
      contactEmail: undefined,
      status: "received",
      createdAt: new Date().toISOString(),
    };
  }

  /** Public form categories → the backend's approved report categories. */
  const REPORT_CATEGORY_BY_LABEL: Record<string, string> = {
    "Unfair allocation": "favouritism",
    "Unofficial payment request": "bribe_request",
    "Duplicate application": "dupe_application",
    "Stand occupancy concern": "other",
    "Handover problem": "other",
    "Other concern": "other",
    bribe_request: "bribe_request",
    favouritism: "favouritism",
    fake_documents: "fake_documents",
    dupe_application: "dupe_application",
    other: "other",
  };

  const REPORT_LABEL_BY_CATEGORY: Record<string, string> = {
    bribe_request: "Unofficial payment request",
    favouritism: "Unfair allocation",
    fake_documents: "Fake documents",
    dupe_application: "Duplicate application",
    other: "Other concern",
  };

  const REPORT_STATUS_BY_WIRE: ReportStatus[] = [
    "received", "under_review", "resolved", "dismissed",
  ];

  interface WireReport {
    id: string;
    reference: string;
    category: string;
    location: string | null;
    status: string;
    created_at: string;
    description?: string;
    contact_email?: string | null;
  }

  function reportToView(wire: WireReport): ReportRecord {
    return {
      id: wire.id,
      reference: wire.reference,
      category: REPORT_LABEL_BY_CATEGORY[wire.category] ?? REPORT_LABEL_BY_CATEGORY.other,
      description: wire.description ?? "",
      location: wire.location ?? undefined,
      contactEmail: wire.contact_email ?? undefined,
      status: REPORT_STATUS_BY_WIRE.includes(wire.status as ReportStatus)
        ? (wire.status as ReportStatus)
        : "received",
      createdAt: wire.created_at,
    };
  }

  /* -------------------------------------------------------------- actions */

  const adapter: StandproofAdapter & {
    logout: () => Promise<void>;
  } = {
    getSnapshot: async () => {
      const context = await loadContext();
      await applyStandCategories();

      const standsPayload = await api.request<WireStands>("/stands?limit=500");
      const stands = standsPayload.stands.map(standToView);

      const empty: Omit<StandproofSnapshot, "stands"> = {
        session: null,
        applications: [],
        allocations: [],
        payments: [],
        notifications: [],
        audit: [],
        reports: [...localReports],
      };
      if (!context) return { ...empty, stands };

      const isAdmin = context.user.role === "admin";

      const [applicationsPayload, allocationsPayload, paymentsPayload, notificationsPayload, reportsPayload] =
        await Promise.all([
          isAdmin
            ? api.request<WireApplications>("/applications")
            : api.request<WireApplications>("/applications/mine"),
          isAdmin
            ? api.request<WireAllocations>("/allocations")
            : api.request<WireAllocations>("/allocations/mine"),
          api.request<WirePayments>("/payments/history"),
          api.request<WireNotifications>("/notifications"),
          // Admin-only concern reports (advisory: an unavailable endpoint
          // must not block the rest of the workspace).
          (isAdmin
            ? api.request<{ reports: WireReport[] }>("/reports")
            : Promise.resolve({ reports: [] })
          ).catch(() => ({ reports: [] as WireReport[] })),
        ]);

      let auditPayload: WireAudit = { logs: [] };
      try {
        auditPayload = await api.request<WireAudit>("/audit-logs?limit=100");
      } catch {
        // Audit is advisory; the rest of the workspace still loads on failure.
      }

      const applications = applicationsPayload.applications.map((item) =>
        applicationToView(item, context),
      );

      // vendor name lookup: vendorId → applicationId → vendorName
      const vendorNameMap = new Map<string, Map<string, string>>();
      applicationsPayload.applications.forEach((item) => {
        if (!item.vendor?.full_name) return;
        const byVendor = vendorNameMap.get(item.vendor_id) ?? new Map<string, string>();
        byVendor.set(item.id, item.vendor.full_name);
        vendorNameMap.set(item.vendor_id, byVendor);
      });

      const payments = paymentsPayload.payments.map((item) =>
        paymentRecord(item, context.vendorId),
      );

      const session = sessionFromMe(context.user);
      const allocations = allocationsPayload.allocations.map((item) =>
        allocationToView(item, vendorNameMap, isAdmin ? undefined : context.fullName),
      );
      if (!isAdmin) {
        await attachEligibility(allocations, context.vendorId);
      }
      return {
        session,
        stands,
        applications,
        allocations,
        payments,
        notifications: notificationsPayload.notifications.map((item) =>
          notificationToView(item, session.id),
        ),
        audit: auditPayload.logs.map((item) => auditToView(item, context)),
        reports: context.user.role === "admin"
          ? reportsPayload.reports.map(reportToView)
          : [...localReports],
      };
    },

    logout: async () => {
      saveAccessToken(null);
    },

    selectPersona: async () => {
      throw new Error("Live sign-in uses your phone number and password. No demonstration profiles exist.");
    },
    createDemoVendor: async () => {
      throw new Error("Create a real account with your NRC and phone number. No demonstration accounts exist.");
    },
    resetDemo: async () => {
      throw new Error("Live records cannot be reset from the browser. Ask the council team for changes.");
    },

    submitApplication: async (input: ApplicationInput) => {
      const context = await loadContext();
      if (!context) throw new Error("Sign in to submit an application.");
      if (context.user.role !== "vendor") {
        throw new Error("Only vendor accounts submit applications.");
      }
      const wire = await api.request<WireApplications["applications"][number]>("/applications", {
        method: "POST",
        body: JSON.stringify({
          business_type: input.businessType,
          preferred_zone: input.preferredZone,
          notes: input.description,
        }),
      });
      return applicationToView(wire, context);
    },

    reviewApplication: async (id: string, decision: "approved" | "rejected", note?: string) => {
      const wire = await api.request<WireApplications["applications"][number]>(
        `/applications/${encodeURIComponent(id)}/review`,
        {
          method: "POST",
          body: JSON.stringify({ decision, reason: note ?? undefined }),
        },
      );
      return applicationToView(wire, null);
    },

    allocate: async (applicationId: string, standId: string) => {
      const wire = await api.request<WireAllocations["allocations"][number]>("/allocations", {
        method: "POST",
        body: JSON.stringify({ application_id: applicationId, stand_id: standId }),
      });
      return allocationToView(wire, new Map(), undefined);
    },

    acceptOffer: async (allocationId: string) => {
      const wire = await api.request<WireAllocations["allocations"][number]>(
        `/allocations/${encodeURIComponent(allocationId)}/accept`,
        { method: "POST", body: JSON.stringify({}) },
      );
      return allocationToView(wire, new Map(), undefined);
    },

    confirmHandover: async (allocationId: string /* role is inferred from the JWT */) => {
      const wire = await api.request<WireAllocations["allocations"][number]>(
        `/allocations/${encodeURIComponent(allocationId)}/handover`,
        { method: "POST", body: JSON.stringify({}) },
      );
      return allocationToView(wire, new Map(), undefined);
    },

    initiatePayment: async (allocationId: string) => {
      const context = await loadContext();
      if (!context) throw new Error("Sign in to view your payment.");
      // Reuse a key only when retrying a request with an unknown outcome.
      let key = paymentIdempotencyKeys.get(allocationId);
      if (!key || !/^[A-Za-z0-9_-]{6,64}$/.test(key)) {
        key = `pay-${crypto.randomUUID()}`;
        paymentIdempotencyKeys.set(allocationId, key);
      }
      const wire = await api.request<WirePayments["payments"][number]>("/payments/initiate", {
        method: "POST",
        headers: { "Idempotency-Key": key },
        body: JSON.stringify({ allocation_id: allocationId }),
      });
      paymentIdempotencyKeys.delete(allocationId);
      // The truth is the backend's provider verification, never the click.
      return paymentRecord(wire, context.vendorId);
    },

    markNotificationRead: async (notificationId: string) => {
      await api.request(`/notifications/${encodeURIComponent(notificationId)}/read`, {
        method: "POST",
      });
    },

    markAllNotificationsRead: async () => {
      const payload = await api.request<WireNotifications>("/notifications?unread_only=true");
      await Promise.allSettled(
        payload.notifications
          .filter((item) => !item.read)
          .map((item) =>
            api.request(`/notifications/${encodeURIComponent(item.id)}/read`, { method: "POST" }),
          ),
      );
    },

    submitReport: async (input: ReportInput) => {
      if (!input.category.trim() || input.description.trim().length < 20) {
        throw new Error("Choose a category and provide at least 20 characters of detail.");
      }
      const wire = await api.request<{ reference?: string; id?: string }>("/reports", {
        method: "POST",
        body: JSON.stringify({
          // The workstation form's categories map onto the backend's approved
          // report categories (unknown labels fall back to "other").
          category: REPORT_CATEGORY_BY_LABEL[input.category.trim()] ?? "other",
          description: input.description,
          location: input.location,
          contact_email: input.contactEmail,
        }),
      });
      const reference =
        (typeof wire.reference === "string" && wire.reference) ||
        (typeof wire.id === "string" && wire.id) ||
        "";
      if (!reference) throw new Error("The report could not be recorded. Try again shortly.");
      const record = reportRecord(input, reference);
      localReports.unshift(record);
      // Local list intentionally minimal: it never contains the report body.
      return record;
    },

    fetchReports: async () => {
      const context = await loadContext();
      if (!context || context.user.role !== "admin") {
        throw new Error("Only administrator accounts can review submitted reports.");
      }
      const wire = await api.request<{ reports: WireReport[] }>("/reports");
      return wire.reports.map(reportToView);
    },

    setReportStatus: async (id: string, status: ReportStatus) => {
      const context = await loadContext();
      if (!context || context.user.role !== "admin") {
        throw new Error("Only administrator accounts can update report status.");
      }
      const wire = await api.request<WireReport>(`/reports/${encodeURIComponent(id)}/status`, {
        method: "POST",
        body: JSON.stringify({ status }),
      });
      return reportToView(wire);
    },

    fetchPermitPdf: async (allocationId: string) => {
      const context = await loadContext();
      if (!context) throw new Error("Sign in to access your permit.");
      const payload = await api.request<ArrayBuffer>(
        `/allocations/${encodeURIComponent(allocationId)}/permit.pdf`,
        { headers: { Accept: "application/pdf" } },
        { binary: true },
      );
      return new Blob([payload], { type: "application/pdf" });
    },
  } as StandproofAdapter & { logout: () => Promise<void> };

  /* ----------------------------------------------------------------- auth */

  const auth = {
    async login(phone: string, password: string) {
      const wire = await api.request<WireAuth>("/auth/login", {
        method: "POST",
        body: JSON.stringify({ phone, password }),
      });
      saveAccessToken(wire.token);
      return sessionFromMe({ ...wire.user, vendor_id: null, unread_notifications: 0 });
    },

    async signup(input: {
      fullName: string;
      nrc: string;
      phone: string;
      businessType: string;
      password: string;
    }) {
      if (!/^\d{6}\/\d{2}\/\d$/.test(input.nrc.trim())) {
        throw new Error("Enter the NRC in the 123456/78/1 format.");
      }
      const wire = await api.request<WireAuth>("/auth/signup", {
        method: "POST",
        body: JSON.stringify({
          full_name: input.fullName,
          phone: input.phone,
          password: input.password,
          nrc: input.nrc,
          business_type: input.businessType,
        }),
      });
      saveAccessToken(wire.token);
      return sessionFromMe({ ...wire.user, vendor_id: null, unread_notifications: 0 });
    },

    logout: async () => {
      try {
        await api.request("/auth/logout", { method: "POST" });
      } catch {
        // JWT is stateless — clearing the local token is the source of truth.
      }
      saveAccessToken(null);
    },
  };

  return { adapter, auth, getAccessToken };
}

export type FlaskBundle = ReturnType<typeof createFlaskAdapter>;

/* Singleton bundle shared by the installer and the auth screens. */
let bundle: FlaskBundle | null = null;

export function flaskBundle(): FlaskBundle {
  if (!bundle) bundle = createFlaskAdapter();
  return bundle;
}

export function flaskAdapter(): StandproofAdapter {
  return flaskBundle().adapter;
}
