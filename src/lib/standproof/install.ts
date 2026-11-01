"use client";

/**
 * One-time live adapter installation.
 *
 * Called from the app shell's client provider. Does nothing in demo mode —
 * when NEXT_PUBLIC_API_URL is unset the labelled demonstration stays active,
 * and when NEXT_PUBLIC_DEMO_MODE === "true" the demo is explicitly selected.
 */

import { useEffect } from "react";
import type { StandproofAdapter } from "@/types/standproof";
import { configureStandproofAdapter } from "./index";
import { createFlaskAdapter } from "./flask";

let installed = false;

/** Call once from the app provider: activates the Flask adapter for live mode. */
export async function installFlaskAdapter(): Promise<StandproofAdapter | null> {
  if (installed) return null;
  if (process.env.NEXT_PUBLIC_DEMO_MODE === "true") return null;
  if (!process.env.NEXT_PUBLIC_API_URL) return null;
  installed = true;
  try {
    const { adapter } = createFlaskAdapter();
    await configureStandproofAdapter(adapter);
    return adapter;
  } catch (error) {
    installed = false;
    throw error;
  }
}

export function useStandproofInstaller() {
  useEffect(() => {
    void installFlaskAdapter().catch((error: unknown) => {
      console.error("Unable to initialize the Pa Market live adapter.", error);
    });
  }, []);
}
