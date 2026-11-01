"use client";

import { useEffect, useSyncExternalStore } from "react";
import type { ServiceMode, StandproofActions, StandproofAdapter, StandproofSnapshot } from "@/types/standproof";
import { demoActions, getDemoSnapshot, hydrateDemo, subscribeDemo } from "./demo";
import { createDemoSnapshot } from "./fixtures";

export * from "@/types/standproof";
export { ZONES, STAND_STATUS_LABELS, DEMO_ADMIN, DEMO_VENDOR } from "./fixtures";
export { ApiError, createApiClient } from "./client";

const EMPTY_SNAPSHOT: StandproofSnapshot = { session: null, stands: [], applications: [], allocations: [], payments: [], notifications: [], audit: [], reports: [] };
const CONFIGURATION_ERROR = "The Flask API URL is configured, but its approved contract adapter is not connected. Live requests are disabled; no demo data is being presented as live data.";
type ServiceState = { snapshot: StandproofSnapshot; loading: boolean; error: string | null; mode: ServiceMode };
const initialMode: ServiceMode = process.env.NEXT_PUBLIC_DEMO_MODE === "true" || !process.env.NEXT_PUBLIC_API_URL ? "demo" : "unconfigured";
const SERVER_STATE: ServiceState = { snapshot: initialMode === "demo" ? createDemoSnapshot() : EMPTY_SNAPSHOT, mode: initialMode, loading: true, error: initialMode === "unconfigured" ? CONFIGURATION_ERROR : null };
let state = SERVER_STATE;
let liveAdapter: StandproofAdapter | null = null;
let mounted = false;
let refreshSequence = 0;
const listeners = new Set<() => void>();
function publish(next: ServiceState) { state = next; listeners.forEach((listener) => listener()); }
export function subscribe(listener: () => void) { listeners.add(listener); return () => { listeners.delete(listener); }; }
function getState() { return state; }
function getServerState() { return SERVER_STATE; }

subscribeDemo(() => {
  if (state.mode === "demo") publish({ ...state, snapshot: getDemoSnapshot(), loading: false });
});

async function refresh() {
  const sequence = ++refreshSequence;
  if (state.mode === "demo") {
    hydrateDemo();
    publish({ snapshot: getDemoSnapshot(), mode: "demo", loading: false, error: null });
    return;
  }
  if (!liveAdapter) { publish({ snapshot: EMPTY_SNAPSHOT, mode: "unconfigured", loading: false, error: CONFIGURATION_ERROR }); return; }
  publish({ ...state, loading: true, error: null });
  try {
    const snapshot = await liveAdapter.getSnapshot();
    if (sequence === refreshSequence) publish({ snapshot, mode: "live", loading: false, error: null });
  }
  catch (error) {
    // Clear stale authorised records when the server cannot establish the current view.
    if (sequence === refreshSequence) publish({ snapshot: EMPTY_SNAPSHOT, mode: "live", loading: false, error: error instanceof Error ? error.message : "Unable to load your records." });
  }
}

/** Call once from the app provider only after agreeing and implementing Flask contracts. */
export async function configureStandproofAdapter(adapter: StandproofAdapter) {
  liveAdapter = adapter;
  publish({ snapshot: EMPTY_SNAPSHOT, mode: "live", loading: true, error: null });
  startLivePolling();
  await refresh();
}

function implementation(): StandproofActions {
  if (state.mode === "demo") return demoActions;
  if (state.mode === "live" && liveAdapter) return liveAdapter;
  throw new Error(CONFIGURATION_ERROR);
}
function wrap<K extends keyof StandproofActions>(name: K): StandproofActions[K] {
  return (async (...args: unknown[]) => {
    if (state.mode !== "demo" && ["selectPersona", "createDemoVendor", "resetDemo"].includes(name)) throw new Error("Demonstration profile and reset actions are unavailable in a live workspace.");
    const target = implementation();
    const action = target[name] as (...params: unknown[]) => Promise<unknown>;
    const result = await action.apply(target, args);
    if (state.mode === "live") {
      if (name === "logout") {
        ++refreshSequence;
        publish({ snapshot: EMPTY_SNAPSHOT, mode: "live", loading: false, error: null });
      } else await refresh();
    }
    return result;
  }) as StandproofActions[K];
}

export const selectPersona = wrap("selectPersona");
export const createDemoVendor = wrap("createDemoVendor");
export const logout = wrap("logout");
export const submitApplication = wrap("submitApplication");
export const reviewApplication = wrap("reviewApplication");
export const allocate = wrap("allocate");
export const acceptOffer = wrap("acceptOffer");
export const confirmHandover = wrap("confirmHandover");
export const initiatePayment = wrap("initiatePayment");
export const markNotificationRead = wrap("markNotificationRead");
export const markAllNotificationsRead = wrap("markAllNotificationsRead");
export const submitReport = wrap("submitReport");
export const fetchReports = wrap("fetchReports");
export const setReportStatus = wrap("setReportStatus");
export const fetchPermitPdf = wrap("fetchPermitPdf");
export const resetDemo = wrap("resetDemo");
export { refresh as refreshStandproof };
export function getSnapshot() { return state.snapshot; }

const actions: StandproofActions = { selectPersona, createDemoVendor, logout, submitApplication, reviewApplication, allocate, acceptOffer, confirmHandover, initiatePayment, markNotificationRead, markAllNotificationsRead, submitReport, fetchReports, setReportStatus, fetchPermitPdf, resetDemo };

/**
 * Live polling: records change from the other side of the workflow (a vendor
 * accepting while an administrator works, an administrator approving while the
 * vendor waits). One refresh per page load leaves both roles looking at stale
 * data; a light interval + focus/online refresh keeps the workspace current
 * without manual reloads. Ticks no-op in demo mode (the demo store publishes
 * its own updates synchronously).
 */
let pollTimer: ReturnType<typeof setInterval> | null = null;
const LIVE_POLL_INTERVAL_MS = 15_000;
export function startLivePolling() {
  if (pollTimer) return;
  const tick = () => { if (state.mode === "live") void refresh(); };
  pollTimer = setInterval(tick, LIVE_POLL_INTERVAL_MS);
  if (typeof document !== "undefined") {
    document.addEventListener("visibilitychange", () => { if (!document.hidden) tick(); });
  }
  if (typeof window !== "undefined") {
    window.addEventListener("focus", tick);
    window.addEventListener("online", tick);
  }
}
export function stopLivePolling() {
  if (pollTimer) { clearInterval(pollTimer); pollTimer = null; }
}

export function useStandproof() {
  const value = useSyncExternalStore(subscribe, getState, getServerState);
  useEffect(() => {
    if (!mounted) { mounted = true; void refresh().then(() => startLivePolling()); }
  }, []);
  return { ...value, ...actions, refresh };
}
