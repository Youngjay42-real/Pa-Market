/** Council-recognised vendor business categories (shared across apply, signup, dashboard). */
export const BUSINESS_CATEGORIES = [
  "Food & Fresh Produce",
  "Electronics & Gadgets",
  "Clothing & Apparel",
  "Hardware & Tools",
  "Beauty & Cosmetics",
  "Handicrafts & Curios",
  "Tailoring & Textiles",
  "Footwear & Leather",
  "Livestock & Poultry",
  "Stationery & Books",
  "General Merchandise",
  "Services & Repairs",
] as const;

export type BusinessCategory = (typeof BUSINESS_CATEGORIES)[number];

/** Market map zones — must match stand.zone values in the database. */
export const MARKET_ZONES = ["Produce", "Textiles", "Hardware", "Food Court"] as const;

export type MarketZone = (typeof MARKET_ZONES)[number];

export const MARKET_ZONE_OPTIONS = [
  { value: "", label: "Any zone" },
  ...MARKET_ZONES.map((zone) => ({ value: zone, label: zone })),
];

/** Zones suited to each business category for fair allocation. */
export const BUSINESS_ZONE_MAP: Record<BusinessCategory, MarketZone[]> = {
  "Food & Fresh Produce": ["Produce", "Food Court"],
  "Electronics & Gadgets": ["Hardware"],
  "Clothing & Apparel": ["Textiles"],
  "Hardware & Tools": ["Hardware"],
  "Beauty & Cosmetics": ["Textiles", "Food Court"],
  "Handicrafts & Curios": ["Textiles", "Produce"],
  "Tailoring & Textiles": ["Textiles"],
  "Footwear & Leather": ["Textiles"],
  "Livestock & Poultry": ["Produce"],
  "Stationery & Books": ["Hardware", "Food Court"],
  "General Merchandise": ["Produce", "Textiles", "Hardware", "Food Court"],
  "Services & Repairs": ["Hardware", "Food Court"],
};

export function getZonesForBusiness(businessType: string): MarketZone[] {
  return (
    BUSINESS_ZONE_MAP[businessType as BusinessCategory] ??
    BUSINESS_ZONE_MAP["General Merchandise"]
  );
}

export function businessCategorySelectOptions() {
  return BUSINESS_CATEGORIES.map((category) => ({
    value: category,
    label: category,
  }));
}
