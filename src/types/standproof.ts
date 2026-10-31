/** Frontend view models. This is not an agreed Flask wire contract. */
export type UserRole = "vendor" | "admin";
export type ServiceMode = "demo" | "unconfigured" | "live";
export type MarketZone = "Produce" | "Textiles" | "Hardware" | "Food Court";
export type StandState = "available" | "occupied" | "reserved" | "pending" | "handover" | "verification" | "suspended";

export interface DemoSession {
  id: string;
  fullName: string;
  role: UserRole;
  phone: string;
  businessType?: string;
}

export interface MarketStand {
  id: string;
  label: string;
  row: number;
  col: number;
  zone: MarketZone;
  section: "A" | "B" | "C" | "D";
  category: string;
  status: StandState;
  area: number;
  monthlyFee: string;
  currency: "USD" | "ZMW";
  vendorName?: string;
  vendorId?: string;
}

export interface StandApplication {
  id: string;
  vendorId: string;
  vendorName: string;
  businessType: string;
  phone: string;
  preferredZone: MarketZone;
  preferredStandId?: string;
  description: string;
  status: "pending" | "approved" | "rejected" | "allocated" | "cancelled";
  queuePosition: number;
  submittedAt: string;
  reviewNote?: string;
}

export interface ApplicationInput {
  businessType: string;
  phone: string;
  preferredZone: MarketZone;
  preferredStandId?: string;
  description: string;
}

export interface Allocation {
  id: string;
  applicationId: string;
  vendorId: string;
  vendorName: string;
  standId: string;
  offeredAt: string;
  acceptedAt?: string;
  vendorConfirmedAt?: string;
  officialConfirmedAt?: string;
  verifiedAt?: string;
  status: "offered" | "accepted" | "handover" | "verified" | "expired" | "cancelled";
}

export interface PaymentRecord {
  id: string;
  allocationId: string;
  vendorId: string;
  amount: string;
  currency: "USD";
  status: "not_eligible" | "eligible" | "pending" | "successful" | "failed" | "refunded" | "disputed";
  providerReference?: string;
  receiptReference?: string;
  createdAt: string;
}

export interface NotificationRecord {
  id: string;
  vendorId: string;
  title: string;
  message: string;
  category: "application" | "allocation" | "handover" | "payment" | "system";
  read: boolean;
  createdAt: string;
  href: string;
}

export interface AuditEvent {
  id: string;
  action: string;
  actor: string;
  entityType: string;
  entityId: string;
  details: string;
  timestamp: string;
}

export interface ReportInput {
  category: string;
  description: string;
  location?: string;
  contactEmail?: string;
}

export interface ReportRecord extends ReportInput {
  id: string;
  status: "received";
  createdAt: string;
}

export interface StandproofSnapshot {
  session: DemoSession | null;
  stands: MarketStand[];
  applications: StandApplication[];
  allocations: Allocation[];
  payments: PaymentRecord[];
  notifications: NotificationRecord[];
  audit: AuditEvent[];
  reports: ReportRecord[];
}

export interface StandproofActions {
  selectPersona(role: UserRole): Promise<DemoSession>;
  createDemoVendor(input: { fullName: string; phone: string; businessType?: string }): Promise<DemoSession>;
  logout(): Promise<void>;
  submitApplication(input: ApplicationInput): Promise<StandApplication>;
  reviewApplication(id: string, decision: "approved" | "rejected", note?: string): Promise<StandApplication>;
  allocate(applicationId: string, standId: string): Promise<Allocation>;
  acceptOffer(allocationId: string): Promise<Allocation>;
  confirmHandover(allocationId: string, role: "vendor" | "official"): Promise<Allocation>;
  initiatePayment(allocationId: string): Promise<PaymentRecord>;
  markNotificationRead(id: string): Promise<void>;
  markAllNotificationsRead(): Promise<void>;
  submitReport(input: ReportInput): Promise<ReportRecord>;
  resetDemo(): Promise<void>;
}

/** Implement this adapter against backend-approved contracts before enabling live mode. */
export interface StandproofAdapter extends StandproofActions {
  getSnapshot(): Promise<StandproofSnapshot>;
}
