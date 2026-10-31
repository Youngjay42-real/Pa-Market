"use client";

/**
 * Pa Market Assistant — floating chat widget.
 *
 * Visual interface (frontend-lead refinable) driven entirely by the chatbot API
 * contract: docs/CHATBOT_CONTRACT.md. No business logic lives in this file.
 */

import { useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useChatbot } from "@/hooks/useChatbot";
import styles from "./ChatWidget.module.css";

function AssistantIcon() {
  return (
    <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M21 11.5a8.4 8.4 0 0 1-8.5 8.4c-1.6 0-3.1-.4-4.3-1.1L3 20l1.2-5.2A8.4 8.4 0 0 1 12.5 3c4.7 0 8.5 3.8 8.5 8.5z" />
      <path d="M8.5 11.5h.01M12.5 11.5h.01M16.5 11.5h.01" />
    </svg>
  );
}

function SparkIcon() {
  return (
    <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M12 3v3M12 18v3M4.9 7.2l2.2 1.4M16.9 15.4l2.2 1.4M4.9 16.8l2.2-1.4M16.9 8.6l2.2-1.4M7.5 12H4M20 12h-3.5" />
      <circle cx="12" cy="12" r="3" />
    </svg>
  );
}

function formatTime(iso: string | null): string {
  if (!iso) return "";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });
}

const ROLE_LABEL: Record<string, string> = {
  guest: "Public mode",
  vendor: "Vendor mode",
  admin: "Administrator mode",
};

export function ChatWidget() {
  const chat = useChatbot();
  const [draft, setDraft] = useState("");
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const node = scrollRef.current;
    if (node) node.scrollTop = node.scrollHeight;
  }, [chat.messages.length, chat.sending, chat.open]);

  const lastUserText = useMemo(() => {
    for (let i = chat.messages.length - 1; i >= 0; i -= 1) {
      const message = chat.messages[i];
      if (message.role === "user") return message.content;
    }
    return "";
  }, [chat.messages]);

  const subtitle = (() => {
    if (chat.connection !== "ready") return chat.connection === "connecting" ? "Connecting…" : "Offline";
    if (chat.identity?.kind === "verified") {
      return `${ROLE_LABEL[chat.identity.role] ?? "Member"} · ${chat.identity.displayName}`;
    }
    return ROLE_LABEL.guest;
  })();

  const submit = () => {
    const text = draft.trim();
    if (!text || chat.sending) return;
    setDraft("");
    void chat.handleSend(text);
  };

  if (!chat.open) {
    return (
      <button
        type="button"
        className={styles.fab}
        onClick={chat.handleOpen}
        aria-label="Open Market Assistant chat"
      >
        <AssistantIcon />
      </button>
    );
  }

  return (
    <section className={styles.panel} role="dialog" aria-label="Pa Market Assistant" aria-modal="false">
      <header className={styles.header}>
        <span className={styles.headerIcon} aria-hidden="true">
          <AssistantIcon />
        </span>
        <div className={styles.headerText}>
          <span className={styles.title}>Market Assistant</span>
          <span className={`${styles.subtitle} ${chat.connection === "ready" ? styles.subtitleReady : styles.subtitleOff}`}>
            <i className={chat.connection === "ready" ? styles.dotReady : styles.dotOff} />
            {subtitle}
          </span>
        </div>
        <button type="button" className={styles.iconBtn} onClick={chat.handleClose} aria-label="Close chat">
          <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
            <path d="M6 6l12 12M18 6L6 18" />
          </svg>
        </button>
      </header>

      <div className={styles.transcript} ref={scrollRef}>
        {chat.connection === "error" && (
          <div className={styles.offline}>
            <p className={styles.offlineText}>The assistant could not be reached.</p>
            <button type="button" className={styles.secondaryBtn} onClick={chat.refresh}>
              Reconnect
            </button>
          </div>
        )}

        {chat.messages.map((message) => {
          const ours = message.role === "user";
          const verified = !ours && message.meta?.verified;
          return (
            <div key={message.id} className={`${styles.row} ${ours ? styles.rowUser : styles.rowAssistant}`}>
              {!ours && verified && (
                <span className={styles.verified}>
                  <SparkIcon /> verified data
                </span>
              )}
              {!ours && message.meta?.degraded && (
                <span className={styles.degraded}>partial — please retry shortly</span>
              )}
              <div className={ours ? styles.bubbleUser : styles.bubbleAssistant}>
                {message.content.split("\n").map((line, index) => (
                  <p key={index} className={styles.line}>
                    {line.startsWith("• ") ? line.slice(2) : line}
                  </p>
                ))}
              </div>
              {message.createdAt && !ours && <span className={styles.stamp}>{formatTime(message.createdAt)}</span>}
            </div>
          );
        })}

        {(chat.sending || chat.connection === "connecting") && (
          <div className={`${styles.row} ${styles.rowAssistant}`} aria-live="polite">
            <div className={styles.bubbleAssistant} data-testid="typing">
              <span className={styles.typing}>
                <i /><i /><i />
              </span>
            </div>
          </div>
        )}

        {!chat.sending && chat.connection === "ready" && chat.suggestedPrompts.length > 0 && (
          <div className={styles.suggestions}>
            {chat.suggestedPrompts.map((prompt) => (
              <button
                key={prompt}
                type="button"
                className={styles.chip}
                onClick={() => void chat.handleSend(prompt)}
                disabled={chat.sending}
              >
                {prompt}
              </button>
            ))}
          </div>
        )}
      </div>

      {chat.error && (
        <div className={styles.errorBar} role="alert">
          <span>{chat.error}</span>
          {lastUserText && (
            <button type="button" className={styles.secondaryBtn} onClick={() => void chat.handleSend(lastUserText)}>
              Retry
            </button>
          )}
        </div>
      )}

      {chat.identity?.kind === "guest" && (
        <div className={styles.guestBar}>
          Public mode —{" "}
          <Link href="/login" className={styles.guestLink}>
            log in
          </Link>{" "}
          for personalised answer checks.
        </div>
      )}

      <footer className={styles.composer}>
        <input
          className={styles.input}
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter" && !event.shiftKey) {
              event.preventDefault();
              submit();
            }
          }}
          placeholder="Ask about stands, applications, payments…"
          maxLength={2000}
          aria-label="Message the Market Assistant"
          disabled={chat.connection !== "ready"}
        />
        <button
          type="button"
          className={styles.sendBtn}
          onClick={submit}
          disabled={chat.sending || chat.connection !== "ready" || !draft.trim()}
          aria-label="Send message"
        >
          <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M22 2L11 13" />
            <path d="M22 2l-7 20-4-9-9-4 20-7z" />
          </svg>
        </button>
      </footer>
    </section>
  );
}
