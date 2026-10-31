import type { AuditEvent, DemoSession, MarketStand, MarketZone, StandproofSnapshot, StandState } from "@/types/standproof";

export const ZONES: readonly MarketZone[] = ["Produce", "Textiles", "Hardware", "Food Court"];
export const STAND_STATUS_LABELS: Record<StandState, string> = {
  available: "Available", occupied: "Occupied", reserved: "Reserved", pending: "Pending allocation",
  handover: "Awaiting handover", verification: "Under verification", suspended: "Suspended",
};

export const DEMO_VENDOR: DemoSession = { id: "VND-001", fullName: "Mary Banda", role: "vendor", phone: "+260 977 000 001", businessType: "Fresh produce" };
export const DEMO_ADMIN: DemoSession = { id: "ADM-001", fullName: "Chanda Mwale", role: "admin", phone: "+260 977 000 900" };

/** Fictional demonstration records. No production vendors or market inventory. */
export function createDemoSnapshot(): StandproofSnapshot {
  const categories = ["Fresh produce", "Textiles & clothing", "Hardware & household", "Food & beverages"];
  const stands: MarketStand[] = Array.from({ length: 120 }, (_, index) => {
    const sectionIndex = Math.floor(index / 30);
    const position = index % 30;
    const roll = (index * 7 + 3) % 20;
    const status: StandState = roll < 11 ? "occupied" : roll < 16 ? "available" : roll < 18 ? "reserved" : roll === 18 ? "verification" : "suspended";
    return {
      id: `ST-${String(index + 1).padStart(3, "0")}`,
      label: `${"ABCD"[sectionIndex]}-${String(position + 1).padStart(2, "0")}`,
      section: "ABCD"[sectionIndex] as MarketStand["section"],
      row: Math.floor(sectionIndex / 2) * 5 + Math.floor(position / 6),
      col: sectionIndex % 2 * 6 + position % 6,
      zone: ZONES[sectionIndex],
      category: categories[sectionIndex],
      status, area: sectionIndex === 2 ? 12 : 9, monthlyFee: sectionIndex === 3 ? "200.00" : "150.00", currency: "ZMW",
      ...(status === "occupied" ? { vendorName: "Allocated vendor", vendorId: `DEMO-OCC-${index + 1}` } : {}),
    };
  });
  stands[13] = { ...stands[13], status: "handover", vendorName: DEMO_VENDOR.fullName, vendorId: DEMO_VENDOR.id };
  stands[17] = { ...stands[17], status: "available", vendorId: undefined, vendorName: undefined };

  const applicants = [
    { id: "APP-2026-0412", vendorId: "VND-001", vendorName: "Mary Banda", businessType: "Fresh produce", phone: "+260 977 000 001", preferredZone: "Produce" as MarketZone, preferredStandId: "ST-014", description: "Seasonal vegetables and locally sourced fresh produce.", status: "allocated" as const, queuePosition: 1, submittedAt: "2026-10-28T06:42:00.000Z" },
    { id: "APP-2026-0413", vendorId: "VND-002", vendorName: "Joseph Phiri", businessType: "Textiles & clothing", phone: "+260 977 000 002", preferredZone: "Textiles" as MarketZone, description: "Chitenge fabrics and tailoring supplies.", status: "pending" as const, queuePosition: 2, submittedAt: "2026-10-29T07:15:00.000Z" },
    { id: "APP-2026-0414", vendorId: "VND-003", vendorName: "Grace Tembo", businessType: "Food & beverages", phone: "+260 977 000 003", preferredZone: "Food Court" as MarketZone, description: "Freshly prepared lunches and non-alcoholic drinks.", status: "pending" as const, queuePosition: 3, submittedAt: "2026-10-29T08:30:00.000Z" },
    { id: "APP-2026-0415", vendorId: "VND-004", vendorName: "Peter Zulu", businessType: "Hardware & household", phone: "+260 977 000 004", preferredZone: "Hardware" as MarketZone, description: "Household repairs and hardware supplies.", status: "approved" as const, queuePosition: 4, submittedAt: "2026-10-30T06:10:00.000Z" },
    { id: "APP-2026-0416", vendorId: "VND-005", vendorName: "Esther Mbewe", businessType: "Fresh produce", phone: "+260 977 000 005", preferredZone: "Produce" as MarketZone, description: "Locally grown fruit and seasonal vegetables.", status: "pending" as const, queuePosition: 5, submittedAt: "2026-10-30T09:22:00.000Z" },
    { id: "APP-2026-0417", vendorId: "VND-006", vendorName: "Daniel Musonda", businessType: "Textiles & clothing", phone: "+260 977 000 006", preferredZone: "Textiles" as MarketZone, description: "Clothing alterations and handmade garments.", status: "pending" as const, queuePosition: 6, submittedAt: "2026-10-31T06:05:00.000Z" },
    { id: "APP-2026-0418", vendorId: "VND-007", vendorName: "Ruth Chileshe", businessType: "Food & beverages", phone: "+260 977 000 007", preferredZone: "Food Court" as MarketZone, description: "Breakfast meals and baked goods.", status: "rejected" as const, queuePosition: 7, submittedAt: "2026-10-31T06:40:00.000Z", reviewNote: "Supporting business information needs to be completed." },
  ];
  const audit: AuditEvent[] = [
    { id: "AUD-001", action: "Offer accepted", actor: "Mary Banda", entityType: "allocation", entityId: "ALC-2026-0086", details: "Demonstration vendor accepted the offer for stand A-14.", timestamp: "2026-10-31T07:40:00.000Z" },
    { id: "AUD-002", action: "Application approved", actor: "Chanda Mwale", entityType: "application", entityId: "APP-2026-0415", details: "Review complete. Awaiting stand selection.", timestamp: "2026-10-31T07:25:00.000Z" },
    { id: "AUD-003", action: "Stand offered", actor: "Chanda Mwale", entityType: "allocation", entityId: "ALC-2026-0086", details: "Stand A-14 offered to Mary Banda after review.", timestamp: "2026-10-31T07:00:00.000Z" },
    { id: "AUD-004", action: "Application received", actor: "Daniel Musonda", entityType: "application", entityId: "APP-2026-0417", details: "Application entered the demonstration review queue.", timestamp: "2026-10-31T06:05:00.000Z" },
    { id: "AUD-005", action: "Application reviewed", actor: "Chanda Mwale", entityType: "application", entityId: "APP-2026-0412", details: "Vendor information reviewed before allocation.", timestamp: "2026-10-30T08:15:00.000Z" },
  ];
  return {
    session: null, stands, applications: applicants,
    allocations: [{ id: "ALC-2026-0086", applicationId: "APP-2026-0412", vendorId: "VND-001", vendorName: "Mary Banda", standId: "ST-014", offeredAt: "2026-10-31T07:00:00.000Z", acceptedAt: "2026-10-31T07:40:00.000Z", status: "accepted" }],
    payments: [{ id: "PAY-DEMO-0086", allocationId: "ALC-2026-0086", vendorId: "VND-001", amount: "3.00", currency: "USD", status: "not_eligible", createdAt: "2026-10-31T07:00:00.000Z" }],
    notifications: [
      { id: "NTF-001", vendorId: "VND-001", title: "Your stand is ready for handover", message: "You accepted stand A-14. Both you and an authorised official must confirm the physical handover before payment becomes eligible.", category: "handover", read: false, createdAt: "2026-10-31T07:40:00.000Z", href: "/vendor/dashboard" },
      { id: "NTF-002", vendorId: "VND-001", title: "A stand offer for you", message: "Stand A-14 in the Produce zone was offered after your application review.", category: "allocation", read: true, createdAt: "2026-10-31T07:00:00.000Z", href: "/vendor/dashboard" },
      { id: "NTF-003", vendorId: "VND-001", title: "Application received", message: "Your application APP-2026-0412 was added to the review queue.", category: "application", read: true, createdAt: "2026-10-28T06:42:00.000Z", href: "/vendor/dashboard" },
    ], audit, reports: [],
  };
}
