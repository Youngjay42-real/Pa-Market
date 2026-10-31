"use client";

import Link from "next/link";
import { Fragment, useEffect, useRef, useState, type ReactNode } from "react";
import { useStandproof } from "@/lib/standproof";
import type { Allocation } from "@/types/standproof";
import { Badge, ConfirmDialog, PageHeading, useToast } from "@/components/workspace/ui";
import styles from "./operations.module.css";

function OpsIcon({ name = "arrow", size = 17 }: { name?: string; size?: number }) {
  const paths: Record<string, ReactNode> = {
    arrow: <><path d="M5 12h14M13 6l6 6-6 6" /></>,
    search: <><circle cx="10.5" cy="10.5" r="6.5" /><path d="m16 16 4.5 4.5" /></>,
    check: <path d="m5 12 4 4L19 6" />,
    clock: <><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></>,
    file: <><path d="M14 3H5v18h14V8zM14 3v5h5M8 12h8M8 16h5" /></>,
    shield: <><path d="m12 3 8 3v5c0 5-8 10-8 10S4 16 4 11V6z" /><path d="m8 11 3 3 5-5" /></>,
    grid: <><rect x="3" y="3" width="7" height="7" rx="1" /><rect x="14" y="3" width="7" height="7" rx="1" /><rect x="3" y="14" width="7" height="7" rx="1" /><rect x="14" y="14" width="7" height="7" rx="1" /></>,
    chevron: <path d="m9 5 7 7-7 7" />,
    download: <><path d="M12 3v12m-5-5 5 5 5-5M4 16v5h16v-5" /></>,
    empty: <><path d="m3 8 9-5 9 5v9l-9 5-9-5zM3 8l9 5 9-5M12 13v9" /></>,
    info: <><circle cx="12" cy="12" r="9" /><path d="M12 11v6M12 7h.01" /></>,
  };
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{paths[name] || paths.arrow}</svg>;
}

const initials = (name: string) => name.split(" ").map(word => word[0]).slice(0, 2).join("");
const date = (value: string) => new Intl.DateTimeFormat("en-GB", { day: "2-digit", month: "short", year: "numeric", timeZone: "Africa/Lusaka" }).format(new Date(value));
const time = (value: string) => new Intl.DateTimeFormat("en-GB", { hour: "2-digit", minute: "2-digit", timeZone: "Africa/Lusaka" }).format(new Date(value));
const messageOf = (error: unknown) => error instanceof Error ? error.message : "Unable to complete this demo action. Please try again.";

function AdminGuard({ children, loading, role }: { children: ReactNode; loading: boolean; role?: string }) {
  if (loading) return <div className={styles.skeleton} aria-label="Loading workspace" role="status" />;
  if (role !== "admin") return <section className={`${styles.panel} ${styles.access}`}><OpsIcon name="shield" size={30} /><h2>Administrator workspace</h2><p>Sign in through the administrator demonstration to review sample applications, record handovers and explore the audit trail.</p><Link href="/login?role=admin" className={styles.primary}>Open administrator sign in <OpsIcon size={15} /></Link><p>Production access must be authorised by the backend.</p></section>;
  return <>{children}</>;
}

function Search({ value, onChange, placeholder }: { value: string; onChange: (value: string) => void; placeholder: string }) {
  return <div className={styles.search}><OpsIcon name="search" size={15} /><input aria-label={placeholder} placeholder={placeholder} value={value} onChange={event => onChange(event.target.value)} /></div>;
}

function Empty({ title = "No records found", description = "Try another search or change your filters." }: { title?: string; description?: string }) {
  return <div className={styles.empty}><OpsIcon name="empty" size={26} /><h3>{title}</h3><p>{description}</p></div>;
}

function Vendor({ name, detail }: { name: string; detail?: string }) {
  return <div className={styles.vendor}><span className={styles.avatar}>{initials(name)}</span><div><strong>{name}</strong>{detail && <small>{detail}</small>}</div></div>;
}

function Pagination({ count, page, onChange, size = 6 }: { count: number; page: number; onChange: (page: number) => void; size?: number }) {
  const pages = Math.max(1, Math.ceil(count / size));
  return <div className={styles.tableFooter}><span>{count === 0 ? "0 records" : `${(page - 1) * size + 1}–${Math.min(page * size, count)} of ${count} records`}</span><div className={styles.pager}><button disabled={page <= 1} aria-label="Previous page" onClick={() => onChange(page - 1)}><span style={{ transform: "rotate(180deg)", display: "flex", padding: 0 }}><OpsIcon name="chevron" size={12} /></span></button><span>{page} / {pages}</span><button disabled={page >= pages} aria-label="Next page" onClick={() => onChange(page + 1)}><OpsIcon name="chevron" size={12} /></button></div></div>;
}

function downloadCsv(name: string, rows: string[][]) {
  const csv = rows.map(row => row.map(value => { const safeValue = /^[=+\-@\t\r]/.test(value) ? `'${value}` : value; return `"${safeValue.replace(/"/g, '""')}"`; }).join(",")).join("\r\n");
  const url = URL.createObjectURL(new Blob(["\ufeff", csv], { type: "text/csv;charset=utf-8;" }));
  const anchor = document.createElement("a"); anchor.href = url; anchor.download = name; anchor.click(); URL.revokeObjectURL(url);
}

export function AdminOverview() {
  const { snapshot, loading } = useStandproof();
  const { stands, applications, allocations, audit, payments } = snapshot;
  const occupied = stands.filter(stand => stand.status === "occupied").length;
  const available = stands.filter(stand => stand.status === "available").length;
  const other = stands.length - occupied - available;
  const pending = applications.filter(application => application.status === "pending").length;
  const handovers = allocations.filter(allocation => !allocation.officialConfirmedAt && allocation.status !== "offered").length;
  const occupancy = stands.length ? Math.round(occupied / stands.length * 100) : 0;
  const circumference = 2 * Math.PI * 70;
  const groups = [{ label: "Occupied", value: occupied, color: "#087f70" }, { label: "Available", value: available, color: "#a8d6c2" }, { label: "Other statuses", value: other, color: "#dfe7e7" }];
  let offset = 0;
  return <AdminGuard loading={loading} role={snapshot.session?.role}><div className={styles.stack}>
    <PageHeading title="Market overview" description="A clear view of your market. A record behind every decision."><Link className={styles.secondary} href="/map"><OpsIcon name="grid" size={15} /> View market map</Link><Link href="/admin/applications" className={styles.primary}>Review applications <OpsIcon size={15} /></Link></PageHeading>
    <div className={styles.metrics}>
      {[{ label: "Total stands", value: stands.length, note: "Across four market zones" }, { label: "Occupied stands", value: occupied, note: `${occupancy}% market occupancy` }, { label: "Available stands", value: available, note: "Ready for allocation review" }, { label: "Pending applications", value: pending, note: "Awaiting your review" }].map(metric => <div key={metric.label} className={styles.metric}><span className={styles.metricLabel}>{metric.label}</span><strong className={styles.metricValue}>{metric.value}</strong><span className={styles.metricNote}>{metric.note}</span></div>)}
    </div>
    <div className={styles.columns}>
      <section className={styles.panel}><header className={styles.panelTitle}><div><h2>Market occupancy</h2><p>Lusaka City Market · Sample records</p></div><Link href="/map" className={styles.link}>Explore map <OpsIcon size={14} /></Link></header><div className={styles.occupancy}><div className={styles.ring}><svg viewBox="0 0 170 170" aria-label={`${occupancy}% occupied`} role="img"><circle cx="85" cy="85" r="70" fill="none" stroke="#eef2f2" strokeWidth="16" />{groups.map(group => { const length = stands.length ? group.value / stands.length * circumference : 0; const result = <circle key={group.label} cx="85" cy="85" r="70" fill="none" stroke={group.color} strokeWidth="16" strokeDasharray={`${Math.max(0, length - (length ? 3 : 0))} ${circumference}`} strokeDashoffset={-offset} />; offset += length; return result; })}</svg><div className={styles.ringCenter}><strong>{occupancy}%</strong><span>of stands occupied</span></div></div><div className={styles.legend}>{groups.map(group => <div className={styles.legendRow} key={group.label}><i className={styles.dot} style={{ background: group.color }} /><span>{group.label}</span><strong>{group.value}</strong></div>)}</div></div></section>
      <section className={styles.panel}><header className={styles.panelTitle}><div><h2>Needs your attention</h2><p>Keep the allocation journey moving</p></div></header>{[{ label: "Applications to review", detail: "Check vendor details and requirements", count: pending, href: "/admin/applications", icon: "file" }, { label: "Handover confirmations", detail: "Record an authorised official's confirmation", count: handovers, href: "/admin/verify", icon: "shield" }, { label: "Payment records", detail: "View eligibility and provider status", count: payments.filter(payment => payment.status === "pending").length, href: "/admin/payments", icon: "clock" }].map(task => <Link key={task.label} href={task.href} className={styles.task}><span className={styles.taskIcon}><OpsIcon name={task.icon} /></span><div className={styles.taskCopy}><strong>{task.label}</strong><p>{task.detail}</p></div><span className={styles.taskCount}>{task.count}</span><OpsIcon name="chevron" size={14} /></Link>)}</section>
    </div>
    <section className={styles.panel}><header className={styles.panelTitle}><div><h2>Application overview</h2><p>Recent submissions and their next steps</p></div><Link href="/admin/applications" className={styles.link}>View all applications <OpsIcon size={14} /></Link></header><div className={styles.tableScroll}><table className={styles.table}><thead><tr><th>Vendor</th><th>Business type</th><th>Preferred zone</th><th>Submitted</th><th>Status</th><th aria-label="Actions" /></tr></thead><tbody>{applications.slice(0, 5).map(application => <tr key={application.id}><td><Vendor name={application.vendorName} detail={application.id} /></td><td>{application.businessType}</td><td>{application.preferredZone}</td><td>{date(application.submittedAt)}</td><td><Badge status={application.status} /></td><td><Link href="/admin/applications" className={styles.action}>Review <OpsIcon size={12} /></Link></td></tr>)}</tbody></table></div>{!applications.length && <Empty title="No applications yet" description="New vendor applications will appear here." />}</section>
    <section className={styles.panel}><header className={styles.panelTitle}><div><h2>Recent activity</h2><p>Every action leaves a trace</p></div><Link href="/admin/audit-logs" className={styles.link}>View audit trail <OpsIcon size={14} /></Link></header><div className={styles.activity}>{audit.slice(0, 3).map(event => <div key={event.id} className={styles.activityItem}><strong>{event.action.replace(/_/g, " ")}</strong><p>{event.actor} · {event.details}</p><time dateTime={event.timestamp}>{date(event.timestamp)} at {time(event.timestamp)} CAT</time></div>)}</div></section>
  </div></AdminGuard>;
}

export function ApplicationManagement() {
  const { snapshot, loading, reviewApplication } = useStandproof();
  const toast = useToast();
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("all");
  const [page, setPage] = useState(1);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [note, setNote] = useState("");
  const [decision, setDecision] = useState<"approved" | "rejected" | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const rows = snapshot.applications.filter(application => (status === "all" || application.status === status) && `${application.vendorName} ${application.id} ${application.businessType}`.toLowerCase().includes(search.toLowerCase()));
  const selected = snapshot.applications.find(application => application.id === selectedId);
  const reviewRef = useRef<HTMLElement>(null);
  useEffect(() => { if (selectedId) reviewRef.current?.scrollIntoView({ block: "start", behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth" }); }, [selectedId]);
  const confirm = async () => {
    if (!selected || !decision || busy) return;
    setBusy(true); setError("");
    try { await reviewApplication(selected.id, decision, note); toast(`Demo application ${decision}. The decision is recorded in the sample audit trail.`); setDecision(null); setPage(1); }
    catch (error) { setError(messageOf(error)); setDecision(null); }
    finally { setBusy(false); }
  };
  return <AdminGuard loading={loading} role={snapshot.session?.role}><div className={styles.stack}>
    <PageHeading title="Applications" description="Review vendor applications with context, consistency and a clear record."><Link href="/admin/allocate" className={styles.secondary}>Manage allocations <OpsIcon size={15} /></Link></PageHeading>
    <section className={styles.panel}><header className={styles.panelTitle}><h2>Vendor applications</h2><Badge status="pending">{snapshot.applications.filter(application => application.status === "pending").length} awaiting review</Badge></header><div className={styles.toolbar}><Search value={search} onChange={value => { setSearch(value); setPage(1); }} placeholder="Search name, reference or business…" /><select aria-label="Filter applications by status" className={styles.select} value={status} onChange={event => { setStatus(event.target.value); setPage(1); }}><option value="all">All statuses</option><option value="pending">Pending review</option><option value="approved">Approved</option><option value="allocated">Allocated</option><option value="rejected">Rejected</option></select><span className={styles.filterCount}>{rows.length} applications</span></div><div className={styles.tableScroll}><table className={styles.table}><thead><tr><th>Vendor</th><th>Business type</th><th>Preferred zone</th><th>Submitted</th><th>Status</th><th>Action</th></tr></thead><tbody>{rows.slice((page - 1) * 6, page * 6).map(application => <tr className={selectedId === application.id ? styles.rowActive : ""} key={application.id}><td><Vendor name={application.vendorName} detail={application.id} /></td><td>{application.businessType}</td><td>{application.preferredZone}</td><td>{date(application.submittedAt)}</td><td><Badge status={application.status} /></td><td><button className={styles.action} onClick={() => { setSelectedId(application.id); setNote(application.reviewNote || ""); setError(""); }}>View details <OpsIcon size={12} /></button></td></tr>)}</tbody></table></div>{!rows.length && <Empty />}<Pagination count={rows.length} page={page} onChange={setPage} /></section>
    {selected && <section ref={reviewRef} className={styles.panel} aria-label="Application review" style={{ scrollMarginTop: 22 }}><header className={styles.panelTitle}><div><h2>Application {selected.id}</h2><p>Review the complete application before making a decision</p></div><button className={styles.action} onClick={() => setSelectedId(null)}>Close details</button></header><div className={styles.panelBody}><Vendor name={selected.vendorName} detail={selected.businessType} /><dl className={styles.details}><div><dt>Telephone</dt><dd>{selected.phone}</dd></div><div><dt>Preferred zone</dt><dd>{selected.preferredZone}</dd></div><div><dt>Queue position</dt><dd>#{selected.queuePosition}</dd></div><div><dt>Application date</dt><dd>{date(selected.submittedAt)}</dd></div></dl><h3 className={styles.subheading}>About this business</h3><p className={styles.sectionIntro}>{selected.description || "No additional business description supplied."}</p><label className={styles.label} htmlFor="review-note">Review note {selected.status === "pending" ? "(required for rejection)" : ""}</label><textarea id="review-note" disabled={selected.status !== "pending"} className={`${styles.field} ${styles.textarea}`} value={note} placeholder="Add context for your decision…" onChange={event => setNote(event.target.value)} maxLength={1000} />{error && <p className={styles.error} role="alert">{error}</p>}{selected.status === "pending" ? <div className={styles.actions}><button className={styles.primary} disabled={busy} onClick={() => setDecision("approved")}><OpsIcon name="check" size={14} /> Approve demo application</button><button className={styles.danger} disabled={busy || !note.trim()} onClick={() => setDecision("rejected")}>Reject demo application</button></div> : selected.status === "approved" ? <div className={styles.actions}><Link href="/admin/allocate" className={styles.primary}>Continue to allocation <OpsIcon size={14} /></Link></div> : <p className={styles.statusNote}>This application has already been reviewed. Current status: {selected.status}.</p>}</div></section>}
    <ConfirmDialog open={!!decision} title={`${decision === "approved" ? "Approve" : "Reject"} this demo application?`} description={`${selected?.vendorName || "This vendor"}'s application will be marked ${decision || "reviewed"} in this demonstration. Your decision and review note will be recorded in the sample audit trail. Approval does not allocate a stand or initiate payment.`} confirmLabel={busy ? "Saving…" : "Confirm demo decision"} onConfirm={confirm} onClose={() => !busy && setDecision(null)} />
  </div></AdminGuard>;
}

export function AllocationManagement() {
  const { snapshot, loading, allocate } = useStandproof();
  const toast = useToast();
  const [applicationId, setApplicationId] = useState("");
  const [standId, setStandId] = useState("");
  const [search, setSearch] = useState("");
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const availableApplications = snapshot.applications.filter(application => application.status === "approved" && `${application.vendorName} ${application.businessType}`.toLowerCase().includes(search.toLowerCase()));
  const selected = snapshot.applications.find(application => application.id === applicationId);
  const selectedStand = snapshot.stands.find(stand => stand.id === standId && stand.status === "available" && stand.zone === selected?.preferredZone);
  const stands = snapshot.stands.filter(stand => stand.status === "available" && stand.zone === selected?.preferredZone);
  const confirm = async () => {
    if (busy) return;
    if (!selected || selected.status !== "approved" || !selectedStand) { setError("Select an approved application and an available stand in its preferred zone."); setConfirming(false); return; }
    setBusy(true); setError("");
    try { await allocate(selected.id, selectedStand.id); toast(`Demo offer created for ${selected.vendorName}. Vendor acceptance and handover are still required.`); setApplicationId(""); setStandId(""); }
    catch (error) { setError(messageOf(error)); }
    finally { setBusy(false); setConfirming(false); }
  };
  return <AdminGuard loading={loading} role={snapshot.session?.role}><div className={styles.stack}>
    <PageHeading title="Stand allocations" description="Match an approved application to an available space, then issue an offer."><Link href="/admin/applications" className={styles.secondary}>Review applications <OpsIcon size={15} /></Link></PageHeading>
    <div className={styles.columns}><section className={styles.panel}><header className={styles.panelTitle}><div><h2>1. Select an application</h2><p>Only approved applications appear here</p></div><Badge status="approved">{availableApplications.length} ready</Badge></header><div className={styles.toolbar}><Search value={search} onChange={setSearch} placeholder="Search approved vendors…" /></div><div className={styles.scrollList}>{availableApplications.map(application => <button key={application.id} aria-pressed={application.id === applicationId} className={`${styles.appChoice} ${application.id === applicationId ? styles.appChoiceActive : ""}`} onClick={() => { setApplicationId(application.id); setStandId(""); setError(""); }}><span className={styles.avatar}>{initials(application.vendorName)}</span><span className={styles.appChoiceContent}><strong>{application.vendorName}</strong><span>{application.businessType} · {application.preferredZone}</span><span>{application.id} · Queue #{application.queuePosition}</span></span><OpsIcon name={application.id === applicationId ? "check" : "chevron"} size={15} /></button>)}{!availableApplications.length && <Empty title="No approved applications" description="Approve a pending application to make it available for an allocation offer." />}</div></section>
    <section className={styles.panel}><header className={styles.panelTitle}><div><h2>2. Choose a stand</h2><p>{selected ? `Preferred zone: ${selected.preferredZone}` : "Select an application to continue"}</p></div></header><div className={styles.panelBody}>{selected ? <><p className={styles.label}>Matched market zone</p><div className={styles.field}>{selected.preferredZone}</div><p className={styles.statusNote}>Only available stands in this application’s preferred zone are shown.</p><p className={styles.sectionLabel}>Available spaces · {stands.length}</p><div className={styles.choiceGrid}>{stands.slice(0, 36).map(stand => <button key={stand.id} aria-pressed={stand.id === standId} className={`${styles.standChoice} ${stand.id === standId ? styles.standSelected : ""}`} onClick={() => setStandId(stand.id)}>{stand.label}{stand.id === standId && <OpsIcon name="check" size={12} />}</button>)}</div>{!stands.length && <Empty title="No stands available" description="There are no available stands in this application’s preferred zone. Select another approved application or check back later." />}{selectedStand && <dl className={styles.details}><div><dt>Stand</dt><dd>{selectedStand.label}</dd></div><div><dt>Zone</dt><dd>{selectedStand.zone}</dd></div><div><dt>Area</dt><dd>{selectedStand.area} m²</dd></div><div><dt>Monthly fee (sample)</dt><dd>{selectedStand.currency} {selectedStand.monthlyFee}</dd></div></dl>}<div className={styles.actions}><button className={`${styles.primary} ${styles.wide}`} disabled={!selectedStand || selected.status !== "approved" || busy} onClick={() => setConfirming(true)}>Create demo allocation offer <OpsIcon size={14} /></button></div></> : <Empty title="Start with a vendor" description="Select an approved application to review the available stands." />}{error && <p className={styles.error} role="alert">{error}</p>}</div></section></div>
    <div className={styles.notice}><OpsIcon name="shield" /><p>An allocation is an offer. The vendor must accept, and both the vendor and an authorised official must confirm physical handover before payment eligibility is established by the backend.</p></div>
    <section className={styles.panel}><header className={styles.panelTitle}><div><h2>Allocation register</h2><p>Track offers through acceptance and verified handover</p></div><Link href="/admin/verify" className={styles.link}>Handover verification <OpsIcon size={14} /></Link></header><div className={styles.tableScroll}><table className={styles.table}><thead><tr><th>Vendor</th><th>Stand</th><th>Offer issued</th><th>Acceptance</th><th>Handover</th><th>Status</th></tr></thead><tbody>{snapshot.allocations.map(allocation => <tr key={allocation.id}><td><Vendor name={allocation.vendorName} detail={allocation.id} /></td><td><strong>{snapshot.stands.find(stand => stand.id === allocation.standId)?.label || allocation.standId}</strong></td><td>{date(allocation.offeredAt)}</td><td>{allocation.acceptedAt ? "Accepted" : "Awaiting vendor"}</td><td>{allocation.verifiedAt ? "Both confirmed" : allocation.vendorConfirmedAt ? "Awaiting official" : "Awaiting vendor"}</td><td><Badge status={allocation.status} /></td></tr>)}</tbody></table></div>{!snapshot.allocations.length && <Empty title="No allocation offers yet" description="Create a demo offer from an approved application above." />}</section>
    <ConfirmDialog open={confirming} title="Issue this demo allocation offer?" description={`Offer stand ${selectedStand?.label || ""} in ${selectedStand?.zone || ""} to ${selected?.vendorName || "this vendor"}? This records an allocation offer in the demonstration. It does not confirm handover or initiate a payment.`} confirmLabel={busy ? "Creating…" : "Confirm demo offer"} onConfirm={confirm} onClose={() => !busy && setConfirming(false)} />
  </div></AdminGuard>;
}

export function HandoverVerification() {
  const { snapshot, loading, confirmHandover } = useStandproof();
  const toast = useToast();
  const [filter, setFilter] = useState("pending");
  const [selected, setSelected] = useState<Allocation | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const rows = snapshot.allocations.filter(allocation => filter === "all" || (filter === "verified" ? !!allocation.verifiedAt : !allocation.verifiedAt));
  const confirm = async () => {
    if (!selected || busy) return;
    setBusy(true); setError("");
    try { await confirmHandover(selected.id, "official"); toast("Demo official handover confirmation recorded. Payment status remains separate from handover verification."); }
    catch (error) { setError(messageOf(error)); }
    finally { setBusy(false); setSelected(null); }
  };
  return <AdminGuard loading={loading} role={snapshot.session?.role}><div className={styles.stack}>
    <PageHeading title="Handover verification" description="Confirm the physical handover. Make every allocation accountable."><Link href="/admin/allocate" className={styles.secondary}>Allocation register <OpsIcon size={15} /></Link></PageHeading>
    <div className={styles.notice}><OpsIcon name="shield" /><p>Record an official confirmation only after a physical handover. Vendor acceptance and vendor confirmation must be present. This screen does not verify a payment or issue a permit.</p></div>
    {error && <p className={styles.error} role="alert">{error}</p>}
    <section className={styles.panel}><header className={styles.panelTitle}><div><h2>Handover register</h2><p>Two confirmations. One traceable record.</p></div><select className={styles.select} aria-label="Filter handovers" value={filter} onChange={event => setFilter(event.target.value)}><option value="pending">Pending verification</option><option value="verified">Verified handovers</option><option value="all">All handovers</option></select></header>{rows.map(allocation => {
      const stand = snapshot.stands.find(stand => stand.id === allocation.standId);
      const canConfirm = !!allocation.acceptedAt && !!allocation.vendorConfirmedAt && !allocation.officialConfirmedAt;
      return <div className={styles.verifyRow} key={allocation.id}><span className={styles.taskIcon}><OpsIcon name="shield" size={19} /></span><div className={styles.verifyContent}><h3>{allocation.vendorName} <span className={styles.ref}>· {stand?.label || allocation.standId}</span></h3><p>{stand?.zone || "Market stand"} · {allocation.id} · Offer issued {date(allocation.offeredAt)}</p><div className={styles.inlineConditions}>{[{ label: "Offer accepted", done: !!allocation.acceptedAt }, { label: "Vendor confirmed", done: !!allocation.vendorConfirmedAt }, { label: "Official confirmed", done: !!allocation.officialConfirmedAt }].map(condition => <span key={condition.label} className={`${styles.condition} ${condition.done ? styles.conditionDone : ""}`}><OpsIcon name={condition.done ? "check" : "clock"} size={12} />{condition.label}</span>)}</div></div>{allocation.verifiedAt ? <Badge status="verified">Handover verified</Badge> : <button className={`${styles.primary} ${styles.smallButton}`} disabled={!canConfirm || busy} onClick={() => setSelected(allocation)}>Confirm demo handover</button>}</div>;
    })}{!rows.length && <Empty title={filter === "verified" ? "No verified handovers" : "No pending handovers"} description="Allocation offers and confirmation progress appear here." />}</section>
    <section className={styles.panel}><header className={styles.panelTitle}><h2>What happens before payment?</h2><Link href="/admin/payments" className={styles.link}>View payment records <OpsIcon size={14} /></Link></header><div className={styles.panelBody}><ul className={styles.checkList}>{[{ title: "A reviewed allocation offer", detail: "An administrator assigns an available stand to an approved application." }, { title: "Explicit vendor acceptance", detail: "The vendor reviews the assigned stand and accepts the offer." }, { title: "Both handover confirmations", detail: "The vendor and an authorised official confirm that the physical handover happened." }, { title: "Backend eligibility and provider verification", detail: "The backend checks the required conditions and verifies the payment result with the provider." }].map((step, index) => <li className={styles.checkItem} key={step.title}><span className={styles.checkCircle}>{index + 1}</span><div><strong>{step.title}</strong><p>{step.detail}</p></div></li>)}</ul></div></section>
    <ConfirmDialog open={!!selected} title="Confirm this demo physical handover?" description={`You are recording the authorised official's confirmation for ${selected?.vendorName || "this vendor"}. In production, confirm only after the stand has physically been handed over. This demonstration writes a sample confirmation and audit event.`} confirmLabel={busy ? "Recording…" : "Record demo confirmation"} onConfirm={confirm} onClose={() => !busy && setSelected(null)} />
  </div></AdminGuard>;
}

export function AuditTrail() {
  const { snapshot, loading } = useStandproof();
  const toast = useToast();
  const [search, setSearch] = useState("");
  const [entity, setEntity] = useState("all");
  const [page, setPage] = useState(1);
  const [expanded, setExpanded] = useState<string | null>(null);
  const rows = snapshot.audit.filter(event => (entity === "all" || event.entityType === entity) && `${event.action} ${event.actor} ${event.entityId} ${event.details}`.toLowerCase().includes(search.toLowerCase()));
  const exportAudit = () => { downloadCsv("standproof-demo-audit.csv", [["Timestamp", "Actor", "Action", "Record type", "Reference", "Details"], ...rows.map(event => [event.timestamp, event.actor, event.action, event.entityType, event.entityId, event.details])]); toast("Filtered sample audit records exported."); };
  return <AdminGuard loading={loading} role={snapshot.session?.role}><div className={styles.stack}>
    <PageHeading title="Audit trail" description="The people, decisions and records behind your market."><button className={styles.secondary} onClick={exportAudit}><OpsIcon name="download" size={15} /> Export sample CSV</button></PageHeading>
    <div className={styles.notice}><OpsIcon name="info" /><p>This is the demonstration activity log stored in this browser. Production audit integrity, permissions and retention must be enforced by the backend.</p></div>
    <section className={styles.panel}><header className={styles.panelTitle}><div><h2>Activity history</h2><p>All timestamps shown in Central Africa Time</p></div><span className={styles.ref}>{rows.length} events</span></header><div className={styles.toolbar}><Search value={search} onChange={value => { setSearch(value); setPage(1); }} placeholder="Search action, person or reference…" /><select aria-label="Filter audit record type" className={styles.select} value={entity} onChange={event => { setEntity(event.target.value); setPage(1); }}><option value="all">All record types</option>{Array.from(new Set(snapshot.audit.map(event => event.entityType))).map(type => <option key={type} value={type}>{type.charAt(0).toUpperCase() + type.slice(1)}</option>)}</select></div><div className={styles.tableScroll}><table className={styles.table}><thead><tr><th>Date & time</th><th>Action</th><th>Performed by</th><th>Record</th><th aria-label="Details" /></tr></thead><tbody>{rows.slice((page - 1) * 6, page * 6).map(event => <Fragment key={event.id}><tr><td><div className={styles.dateCell}>{date(event.timestamp)}<span>{time(event.timestamp)} CAT</span></div></td><td><strong>{event.action.replace(/_/g, " ")}</strong><small>{event.entityType}</small></td><td>{event.actor}</td><td className={styles.mono}>{event.entityId}</td><td><button className={styles.action} aria-expanded={expanded === event.id} onClick={() => setExpanded(expanded === event.id ? null : event.id)}>{expanded === event.id ? "Hide" : "Details"} <OpsIcon name="chevron" size={12} /></button></td></tr>{expanded === event.id && <tr><td colSpan={5} className={styles.auditDetail}><strong>Event {event.id}</strong><br />{event.details}</td></tr>}</Fragment>)}</tbody></table></div>{!rows.length && <Empty />}<Pagination count={rows.length} page={page} onChange={setPage} /></section>
  </div></AdminGuard>;
}

export function PaymentRegister() {
  const { snapshot, loading } = useStandproof();
  const toast = useToast();
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("all");
  const [page, setPage] = useState(1);
  const rows = snapshot.payments.filter(payment => (status === "all" || payment.status === status) && `${payment.id} ${payment.providerReference || ""} ${snapshot.allocations.find(allocation => allocation.id === payment.allocationId)?.vendorName || ""}`.toLowerCase().includes(search.toLowerCase()));
  const exportPayments = () => { downloadCsv("standproof-demo-payments.csv", [["Payment", "Allocation", "Amount", "Currency", "Status", "Provider reference", "Created"], ...rows.map(payment => [payment.id, payment.allocationId, payment.amount, payment.currency, payment.status, payment.providerReference || "", payment.createdAt])]); toast("Filtered sample payment records exported."); };
  return <AdminGuard loading={loading} role={snapshot.session?.role}><div className={styles.stack}>
    <PageHeading title="Payment records" description="Eligibility, provider references and payment status in one place."><button className={styles.secondary} onClick={exportPayments}><OpsIcon name="download" size={15} /> Export sample CSV</button></PageHeading>
    <div className={styles.notice}><OpsIcon name="shield" /><p>DevDraft is not connected in this demonstration. No money moves. Payment success and receipts require a verified backend response; administrators cannot manually mark a payment successful.</p></div>
    <section className={styles.panel}><header className={styles.panelTitle}><div><h2>Transaction register</h2><p>Sample records · Values are displayed in their recorded currency</p></div></header><div className={styles.miniStats}><div><i className={styles.dot} style={{ background: "#8db7a5" }} /><strong>{snapshot.payments.filter(payment => payment.status === "eligible").length}</strong> eligible</div><div><i className={styles.dot} style={{ background: "#d5af73" }} /><strong>{snapshot.payments.filter(payment => payment.status === "pending").length}</strong> pending</div><div><i className={styles.dot} style={{ background: "#bcc8ce" }} /><strong>{snapshot.payments.filter(payment => payment.status === "not_eligible").length}</strong> awaiting conditions</div></div><div className={styles.toolbar}><Search value={search} onChange={value => { setSearch(value); setPage(1); }} placeholder="Search vendor or payment reference…" /><select aria-label="Filter payment status" className={styles.select} value={status} onChange={event => { setStatus(event.target.value); setPage(1); }}><option value="all">All payment statuses</option><option value="not_eligible">Not eligible</option><option value="eligible">Eligible for payment</option><option value="pending">Payment pending</option><option value="successful">Successful</option><option value="failed">Failed</option><option value="refunded">Refunded</option></select></div><div className={styles.tableScroll}><table className={styles.table}><thead><tr><th>Vendor / payment</th><th>Stand</th><th>Amount</th><th>Handover</th><th>Status</th><th>Provider reference</th></tr></thead><tbody>{rows.slice((page - 1) * 6, page * 6).map(payment => { const allocation = snapshot.allocations.find(allocation => allocation.id === payment.allocationId); const stand = snapshot.stands.find(stand => stand.id === allocation?.standId); return <tr key={payment.id}><td><Vendor name={allocation?.vendorName || "Vendor record"} detail={payment.id} /></td><td><strong>{stand?.label || "—"}</strong><small>{allocation?.id}</small></td><td><strong>{payment.currency} {payment.amount}</strong></td><td>{allocation?.verifiedAt ? <span className={styles.positive}>Both confirmed</span> : "Awaiting confirmations"}</td><td><Badge status={payment.status}>{payment.status === "pending" ? "Payment pending" : payment.status === "eligible" ? "Eligible for payment" : payment.status === "successful" ? "Payment successful" : undefined}</Badge></td><td className={styles.mono}>{payment.providerReference || "Not issued"}</td></tr>; })}</tbody></table></div>{!rows.length && <Empty title="No matching payment records" description="Payment records appear as allocations progress. Try changing the filter." />}<Pagination count={rows.length} page={page} onChange={setPage} /></section>
    <section className={styles.panel}><div className={styles.panelBody}><h2 className={styles.subheading}>Payment accountability</h2><p className={styles.sectionIntro}>An application approval does not authorise payment. Allocation acceptance, physical handover confirmations and backend eligibility checks must be completed first. Provider verification remains the source of truth for a transaction result.</p><Link href="/admin/verify" className={styles.link}>Review handover conditions <OpsIcon size={14} /></Link></div></section>
  </div></AdminGuard>;
}
