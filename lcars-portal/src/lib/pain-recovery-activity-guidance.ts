export const ACTIVITY_ROUTES=['start','smaller','later','pause','alternative','resume'] as const;
export type ActivityRoute=typeof ACTIVITY_ROUTES[number];
export function isActivityRoute(value:unknown):value is ActivityRoute{return typeof value==='string'&&(ACTIVITY_ROUTES as readonly string[]).includes(value);}
export function activityGuidanceBoundary(route:ActivityRoute){return route==='pause'?'safety_hold':route==='start'||route==='resume'?'follow_peter_plan':route==='alternative'?'valued_activity_alternative':'adapt_without_catch_up';}
