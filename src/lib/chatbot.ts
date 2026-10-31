"use client";

/**
 * Chatbot API client — implements docs/CHATBOT_CONTRACT.md exactly.
 *
 * Owned by Developer 3 (chatbot engineer). The chat widget, the chatbot hook and
 * any future consumer should go through these functions — there is deliberately
 * no chatbot business logic in the Next.js app; Flask owns the intelligence.
 */

import type { ChatIdentityInfo, ChatMessageDto, ChatSessionResponse } from "./chatbotTypes";

export const CHAT_BASE = "/api/v1/chatbot";

function resolveBase(): string {
  // StandProof's adapter requires NEXT_PUBLIC_API_URL to end in /api/v1.
  // The chatbot contract paths already carry /api/v1 — dedupe the suffix so
  // both clients can share one environment variable without double prefixes.
  const raw = (process.env.NEXT_PUBLIC_API_URL || "").replace(/\/$/, "");
  const base = raw.replace(/\/api\/v1$/, "");
  return `${base}${CHAT_BASE}`;
}

export class ChatApiError extends Error {
  code: string;
  status: number;
  retryAfter?: number;

  constructor(code: string, status: number, message: string, retryAfter?: number) {
    super(message);
    this.code = code;
    this.status = status;
    this.retryAfter = retryAfter;
  }
}

async function parseResponse<T>(response: Response): Promise<T> {
  let body: unknown = null;
  try {
    body = await response.json();
  } catch {
    // non-JSON (e.g. proxy error) — fall through
  }

  if (!response.ok) {
    const envelope = body as { error?: { code?: string; message?: string } } | null;
    throw new ChatApiError(
      envelope?.error?.code || "request_failed",
      response.status,
      envelope?.error?.message || "The assistant is unavailable right now. Please try again.",
      Number(response.headers.get("Retry-After") || 0) || undefined,
    );
  }
  return (body ?? {}) as T;
}

/** Start a chat session. Pass `identity` for logged-in users; omit for a guest. */
export async function createChatSession(identity: ChatIdentityInfo | null): Promise<ChatSessionResponse> {
  const response = await fetch(`${resolveBase()}/sessions`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(identity ? { identity } : {}),
    credentials: "omit",
  });
  return parseResponse<ChatSessionResponse>(response);
}

/** Send one user message and receive the assistant's full turn. */
export async function sendChatMessage(
  sessionId: string,
  chatToken: string,
  content: string,
): Promise<{ userMessage: ChatMessageDto; assistantMessage: ChatMessageDto; suggestedPrompts: string[] }> {
  const response = await fetch(`${resolveBase()}/sessions/${encodeURIComponent(sessionId)}/messages`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${chatToken}`,
    },
    body: JSON.stringify({ content }),
    credentials: "omit",
  });
  return parseResponse(response);
}

/** Replay the transcript for a stored session. */
export async function getChatHistory(
  sessionId: string,
  chatToken: string,
): Promise<{ sessionId: string; messages: ChatMessageDto[] }> {
  const response = await fetch(`${resolveBase()}/sessions/${encodeURIComponent(sessionId)}/messages`, {
    headers: { Authorization: `Bearer ${chatToken}` },
    credentials: "omit",
  });
  return parseResponse(response);
}

/** Check service health (controls the online/offline pill in the widget). */
export async function getChatHealth(): Promise<{ status: string; assistant: { llmProvider: string } }> {
  const response = await fetch(`${resolveBase()}/health`, { credentials: "omit" });
  if (!response.ok) {
    throw new ChatApiError("health_failed", response.status, "Assistant offline");
  }
  return parseResponse(response);
}
