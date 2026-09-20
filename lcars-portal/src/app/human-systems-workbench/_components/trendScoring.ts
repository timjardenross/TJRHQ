// Shared capacity_state -> 0-100 score map for the Human Systems trend
// charts. Split out of trends/page.tsx (2026-09-20, mission USS-TJR-
// MSN-0394 deep Human Systems mockup alignment pass) because Next.js's
// page-export validation only allows a page.tsx to export the recognized
// page fields (metadata, generateStaticParams, etc.) — the same
// constraint route.ts's own doc comment already noted for handler files
// (see app/api/human-systems/trends/route.ts). trends/page.tsx re-exports
// this for its own use so there is exactly one copy of the map, not two
// drifting ones between the Trends page and the Overview tab's Capacity
// Trend chart (CapacityTrendCard.tsx).
export const TREND_CAPACITY: Record<string, number> = { green: 85, orange: 55, red: 20 };
