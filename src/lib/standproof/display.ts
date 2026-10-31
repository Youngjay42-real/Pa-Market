/** Display helpers for live backend fields the wire contract does not carry.
 * Do not invent market data: unlabeled unknowns are shown as "not recorded". */
export function formatArea(area: number): string {
  return Number.isFinite(area) && area > 0 ? `${area} m²` : "Not recorded";
}
