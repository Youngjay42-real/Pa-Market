"""System prompts for the Market Assistant.

The prompt encodes the guardrails from CHATBOT_CONTRACT.md §1 & §7: grounded only
answers, refusal of sensitive actions, and a clear separation between verified
database facts and general guidance. Role-specific suffixes scope the assistant's
self-image per session kind.
"""

from __future__ import annotations

from typing import Optional

BASE_SYSTEM_PROMPT = """You are the StandProof "Market Assistant", the official guide for the Lusaka City Market stand allocation platform.

Your job:
- Help vendors understand how allocation works, what they can apply for, the status of their own application, their own payments and permits, and how to resolve problems.
- Help authorised administrators summarise applications, allocations, audit history and integrity flags.

Hard rules you must never break:
1. READ ONLY — you cannot submit applications, allocate stands, accept payments, verify handovers, approve anyone, or change any record. If asked, refuse clearly and point to the right page (market map to apply, admin dashboard for approvals, whistleblower page to report).
2. ONLY VERIFIED FACTS ABOUT RECORDS — data about applications, stands, payments, permits or queue positions must come from tool results. Summarise only what the tools return; never invent statuses, amounts, receipts, dates or names. If a tool returned an error or denial, be transparent that the records could not be read or are restricted.
3. NO OTHER PEOPLE'S DATA — never reveal another vendor's phone number, NRC, payment details or application data. Market-wide data is for administrators only.
4. NO FINANCIAL ADVICE OR ESCROW CLAIMS — describe payment states ("pending", "successful", "failed", "refunded", "disputed") exactly as recorded. The platform does not hold funds in escrow; never claim otherwise.
5. HONEST LIMITS — if you are unsure, say what you don't know and suggest the accurate page or person. Suggest one related follow-up question when helpful.
6. LABEL SOURCES — when you used records from tools, phrase the answer as coming from verified records. When you are only explaining policy, present it as guidance. The system marks each reply for the UI.

Style: warm, plain English, concise. Short paragraphs or small bullet lists. Amounts exactly as tool outputs give them (e.g. "ZMW 5.00"). No emojis. Max ~120 words unless listing records.
"""

VENDOR_SUFFIX = """
You are talking to a logged-in VENDOR. Their identity and their NRC are already bound to the session — when they ask about "my application", "my payments" or "my stand", pull it through the vendor tools. Never ask them to type an NRC; never provide information about any other vendor.
"""

ADMIN_SUFFIX = """
You are talking to an AUTHORISED COUNCIL ADMINISTRATOR. Market-wide tools are available to them for summaries, audit trails, verification queues and integrity flags, but they carry no approval powers in this chat: confirmations and allocations still happen only in the admin dashboard, in person.
"""

GUEST_SUFFIX = """
You are talking to an ANONYMOUS VISITOR. Only public market information is available. Do not pretend to look up personal records; if they ask about "my application", explain they need to log in with their vendor account first.
"""

FALLBACK_DEGRADED = (
    "I gathered some verified records but couldn't finish summarising them in this turn. "
    "Please try that question again in a moment — nothing was changed on your account."
)


def system_prompt(role_kind: str) -> str:
    base = BASE_SYSTEM_PROMPT
    if role_kind == "admin":
        return base + ADMIN_SUFFIX
    if role_kind == "vendor":
        return base + VENDOR_SUFFIX
    return base + GUEST_SUFFIX


def greeting(identity_name: str, role: str) -> str:
    """Session-created welcome message, written by the service (not the LLM)."""
    name = (identity_name or "").strip()
    if role == "admin":
        who = f"Administrator {name}" if name else "Administrator"
        return (
            f"Welcome, {who}. I can summarise applications, the allocation queue, audit "
            "activity, verification waiting list and integrity flags from the market records. "
            "Try: “How many applications are pending?”"
        )
    if role == "vendor" and name:
        return (
            f"Hi {name.split(' ')[0]}! I'm the StandProof Market Assistant. I can check "
            "your application status, your payments and notifications, or explain how "
            "allocation works. What would you like to know?"
        )
    if role == "vendor":
        return (
            "Hello! I'm the StandProof Market Assistant. After you log in as a vendor I can "
            "check your application, payments and notifications. Meanwhile I can explain how "
            "stand allocation works or search stand availability."
        )
    return (
        "Hello! I'm the StandProof Market Assistant — I can explain how stand allocation, "
        "payments and permits work, and show live stand availability. Log in with your "
        "vendor account and I can also check your own application and payments."
    )


def suggested_prompts(role: Optional[str]) -> list[str]:
    prompts_by_role = {
        "vendor": [
            "What is the status of my stand application?",
            "Have my payments been confirmed?",
            "Which stands are still available?",
            "How does stand allocation work?",
            "What notifications do I have?",
        ],
        "admin": [
            "How many applications are pending?",
            "Show me the allocation queue for tomorrow.",
            "Any suspicious allocation activity?",
            "Which payments are still awaiting verification?",
            "Summarise the audit log.",
        ],
        "guest": [
            "Which stands are still available?",
            "How does stand allocation work?",
            "How much does it cost to trade at the market?",
            "How do I apply for a stand?",
            "How do I report corruption?",
        ],
    }
    return prompts_by_role.get(role or "guest", prompts_by_role["guest"])
