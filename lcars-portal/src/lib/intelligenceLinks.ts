// The ONE builder for links into the consolidated Intelligence experience. /intelligence-workbench is the single home;
// the retired /intelligence page is only a pointer. Python mirror: intelligence/tiered_brief.py (INTELLIGENCE_HOME_PATH,
// INCIDENTS_TAB, PRODUCTS_TAB, incident_link); tests/test_intelligence_links.py asserts the two agree and that the route and tabs exist.

export const INTELLIGENCE_HOME_PATH = '/intelligence-workbench';
export const INCIDENTS_TAB = 'incidents';
export const PRODUCTS_TAB = 'products';
export const SOURCES_TAB = 'sources';

export function intelligenceTabHref(tab: string, anchor?: string): string {
  return `${INTELLIGENCE_HOME_PATH}?tab=${tab}${anchor ? `#${anchor}` : ''}`;
}

export function incidentHref(incidentKey: string): string {
  return intelligenceTabHref(INCIDENTS_TAB, incidentKey);
}

export function productHref(productKey?: string): string {
  return intelligenceTabHref(PRODUCTS_TAB, productKey);
}
