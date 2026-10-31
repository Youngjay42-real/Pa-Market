"use client";

/**
 * Chatbot state hook — session lifecycle, transcript, optimistic sending.
 *
 * Design (per docs/CHATBOT_CONTRACT.md §10):
 * - the session is created lazily on first open
 * - {sessionId, chatToken} persists in sessionStorage and history replays on reload
 * - identity auto-derives from the app session user ("app_user" in sessionStorage)
 * - errors are surfaced for a friendly Retry; nothing ever marks a fake answer
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ChatApiError, createChatSession, getChatHistory, sendChatMessage } from "@/lib/chatbot";
import type { ChatIdentityInfo, ChatMessageDto } from "@/lib/chatbotTypes";

const STORAGE_KEY = "standproof_chat_v1";
const APP_USER_KEY = "app_user";

export type ChatConnection = "connecting" | "ready" | "error";

interface StoredConversation {
  sessionId: string;
  chatToken: string;
  identityKind: "guest" | "verified";
  identityRole: string;
  displayName: string;
  suggestedPrompts: string[];
}

interface SessionUser {
  id: string;
  phone: string;
  fullName: string;
  role: string;
  nrc?: string | null;
  businessType?: string | null;
}

function readSessionUser(): SessionUser | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.sessionStorage.getItem(APP_USER_KEY);
    return raw ? (JSON.parse(raw) as SessionUser) : null;
  } catch {
    return null;
  }
}

function identityFromUser(user: SessionUser | null): ChatIdentityInfo | null {
  if (!user || !user.phone || !user.fullName) return null;
  return {
    id: user.id,
    phone: user.phone,
    fullName: user.fullName,
    role: user.role === "admin" ? "admin" : "vendor",
    nrc: user.nrc ?? undefined,
    businessType: user.businessType ?? undefined,
  };
}

function loadStored(): StoredConversation | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.sessionStorage.getItem(STORAGE_KEY);
    return raw ? (JSON.parse(raw) as StoredConversation) : null;
  } catch {
    return null;
  }
}

function store(conversation: StoredConversation | null) {
  if (typeof window === "undefined") return;
  if (!conversation) {
    window.sessionStorage.removeItem(STORAGE_KEY);
    return;
  }
  window.sessionStorage.setItem(STORAGE_KEY, JSON.stringify(conversation));
}

export interface ChatbotState {
  open: boolean;
  messages: ChatMessageDto[];
  suggestedPrompts: string[];
  connection: ChatConnection;
  sending: boolean;
  error: string | null;
  identity: { kind: "guest" | "verified"; role: string; displayName: string } | null;
}

export function useChatbot() {
  const [open, setOpen] = useState(false);
  const [connection, setConnection] = useState<ChatConnection>("connecting");
  const [messages, setMessages] = useState<ChatMessageDto[]>([]);
  const [suggestedPrompts, setSuggestedPrompts] = useState<string[]>([]);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [identity, setIdentity] = useState<StoredConversation | null>(null);

  const conversationRef = useRef<StoredConversation | null>(null);
  const startedRef = useRef(false);
  const sendingRef = useRef(false);

  useEffect(() => {
    conversationRef.current = loadStored();
    if (conversationRef.current) {
      setIdentity(conversationRef.current);
      setSuggestedPrompts(conversationRef.current.suggestedPrompts ?? []);
    }
  }, []);

  /** Create (or reopen) the session and load the transcript. */
  const ensureConversation = useCallback(async () => {
    setConnection("connecting");
    setError(null);

    const appUser = readSessionUser();
    const identityPayload = identityFromUser(appUser);
    const stored = conversationRef.current;

    try {
      // Reuse a stored verified session when the logged-in user hasn't changed.
      if (
        stored &&
        stored.identityKind === "verified" &&
        stored.displayName === appUser?.fullName &&
        stored.identityRole === (appUser?.role ?? "vendor")
      ) {
        try {
          const history = await getChatHistory(stored.sessionId, stored.chatToken);
          conversationRef.current = stored;
          setMessages(history.messages as ChatMessageDto[]);
          setConnection("ready");
          return;
        } catch {
          // expired token — fall through and start fresh below
        }
      }

      const fresh = await createChatSession(identityPayload);
      const conversation: StoredConversation = {
        sessionId: fresh.sessionId,
        chatToken: fresh.chatToken,
        identityKind: fresh.identity.kind,
        identityRole: fresh.identity.role,
        displayName: fresh.identity.displayName,
        suggestedPrompts: fresh.suggestedPrompts,
      };
      conversationRef.current = conversation;
      store(conversation);
      setIdentity(conversation);
      setMessages(
        fresh.greeting
          ? [{ id: "greeting", role: "assistant", content: fresh.greeting, createdAt: null, meta: { verified: false, toolsUsed: [], degraded: false } }]
          : [],
      );
      setSuggestedPrompts(fresh.suggestedPrompts);
      setConnection("ready");
      setError(null);
    } catch (err) {
      setConnection("error");
      setError(err instanceof ChatApiError ? err.message : "The assistant is unreachable right now.");
    }
  }, []);

  const handleOpen = useCallback(() => {
    setOpen(true);
    if (!startedRef.current) {
      startedRef.current = true;
      void ensureConversation();
    }
  }, [ensureConversation]);

  const handleClose = useCallback(() => setOpen(false), []);

  const restart = useCallback(() => {
    conversationRef.current = null;
    store(null);
    startedRef.current = false;
    setMessages([]);
    setSuggestedPrompts([]);
    setOpen(true);
    void ensureConversation();
  }, [ensureConversation]);

  const handleSend = useCallback(
    async (content: string) => {
      const conversation = conversationRef.current;
      const text = content.trim();
      if (!text || sendingRef.current || !conversation) return;

      sendingRef.current = true;
      setSending(true);
      setError(null);

      const optimisticId = `local-${Date.now()}`;
      setMessages((current) => [
        ...current,
        {
          id: optimisticId,
          role: "user",
          content: text,
          createdAt: new Date().toISOString(),
          meta: { verified: false, toolsUsed: [], degraded: false },
        },
      ]);

      try {
        const turn = await sendChatMessage(conversation.sessionId, conversation.chatToken, text);
        setMessages((current) =>
          [
            ...current.filter((message) => message.id !== optimisticId),
            turn.userMessage,
            turn.assistantMessage,
          ].filter(Boolean) as ChatMessageDto[],
        );
        if (turn.suggestedPrompts?.length) {
          setSuggestedPrompts(turn.suggestedPrompts);
        }
      } catch (err) {
        // keep the optimistic message; show retry affordance
        setError(
          err instanceof ChatApiError
            ? err.message
            : "Message could not be delivered. Please try again.",
        );
      } finally {
        sendingRef.current = false;
        setSending(false);
      }
    },
    [],
  );

  /** A logged-in/unlogged swap invalidates the stored conversation. */
  useEffect(() => {
    const appUser = readSessionUser();
    const role = appUser?.role ?? "guest";
    if (conversationRef.current && conversationRef.current.identityRole !== role) {
      conversationRef.current = null;
      store(null);
      setMessages([]);
      setSuggestedPrompts([]);
    }
  }, [open]);

  const suggested = useMemo(
    () => suggestedPrompts.slice(0, 4),
    [suggestedPrompts],
  );

  const state: ChatbotState = {
    open,
    messages,
    suggestedPrompts: suggested,
    connection,
    sending,
    error,
    identity: identity
      ? { kind: identity.identityKind, role: identity.identityRole, displayName: identity.displayName }
      : null,
  };

  return { ...state, handleOpen, handleClose, handleSend, restart, refresh: ensureConversation };
}
