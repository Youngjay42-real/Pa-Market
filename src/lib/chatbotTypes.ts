/**
 * Shared chat types mirroring docs/CHATBOT_CONTRACT.md.
 * Owned by Developer 3 (chatbot engineer) per the team split.
 */

export type ChatRole = "user" | "assistant";

export interface ChatMessageMeta {
  verified: boolean;
  toolsUsed: string[];
  degraded: boolean;
}

export interface ChatMessageDto {
  id: string;
  role: ChatRole;
  content: string;
  createdAt: string | null;
  meta?: ChatMessageMeta;
}

export interface ChatIdentityInfo {
  id?: string;
  phone: string;
  fullName: string;
  role: string;
  nrc?: string | null;
  businessType?: string | null;
}

export interface ChatSessionResponse {
  sessionId: string;
  chatToken: string;
  identity: { kind: "guest" | "verified"; role: string; displayName: string };
  greeting: string;
  suggestedPrompts: string[];
}
