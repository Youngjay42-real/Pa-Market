"use client";

import Link from "next/link";
import type { ReactNode } from "react";
import { useStandproof } from "@/lib/standproof";
import s from "./vendor-workspace.module.css";

export const money = (amount: string, currency = "USD") => new Intl.NumberFormat("en-ZM", { style: "currency", currency }).format(Number(amount));
export const date = (value?: string, time = false) => value ? new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "short", year: "numeric", ...(time ? { hour: "2-digit", minute: "2-digit" } as const : {}), timeZone: "Africa/Lusaka" }).format(new Date(value)) : "Awaiting confirmation";
export const label = (value: string) => value.replace(/_/g, " ").replace(/^./, (letter) => letter.toUpperCase());
export function Status({ value }: { value: string }) { return <span className={`${s.badge} ${["pending", "offered", "not_eligible", "handover"].includes(value) ? s.pending : ["rejected", "failed"].includes(value) ? s.red : ["refunded"].includes(value) ? s.neutral : value === "verification" ? s.purple : ""}`}>{value === "handover" ? "Awaiting handover" : value === "verification" ? "Under verification" : label(value)}</span>; }
export function Heading({ title, description, children }: { title: string; description: string; children?: ReactNode }) { return <header className={s.heading}><div><h1>{title}</h1><p>{description}</p></div>{children && <div className={s.actions}>{children}</div>}</header>; }
export function Detail({ title, children }: { title: string; children: ReactNode }) { return <div className={s.detail}><dt>{title}</dt><dd>{children}</dd></div>; }
export function Panel({ title, description, children, action }: { title: string; description?: string; children: ReactNode; action?: ReactNode }) { return <section className={s.panel}><header className={s.panelHead}><div><h2>{title}</h2>{description && <p>{description}</p>}</div>{action}</header><div className={s.body}>{children}</div></section>; }
export function AccountRequired({ title = "Your market journey starts here", description = "Sign in to see your own applications, stand offers, and payment records." }: { title?: string; description?: string }) { const service = useStandproof(); return <section className={s.empty}><div className={s.emptyMark} aria-hidden="true">◎</div><h2>{title}</h2><p>{description}</p><div className={s.actions}><Link href="/login" className={s.button}>Sign in</Link>{service.mode === "demo" && <button className={s.secondary} onClick={() => { void service.selectPersona("vendor"); }}>Explore vendor demo</button>}</div>{service.error && <p className={s.error} role="alert">{service.error}</p>}</section>; }
export function ServiceProblem({ message }: { message: string }) { return <div className={s.error} role="alert">{message} The frontend needs the backend team’s approved API contract before live records can be displayed.</div>; }
export function LoadingPage() { return <div className={s.notice} role="status">Loading your workspace…</div>; }
