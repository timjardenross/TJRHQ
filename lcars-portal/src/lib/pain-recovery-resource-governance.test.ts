import { describe, expect, it } from 'vitest';
import { allResourcesGoverned, resourceHealthReport } from './pain-recovery-resource-governance';

describe('phase 6 resource governance',()=>{
  it('keeps every approved source HTTPS and metadata-complete',()=>expect(allResourcesGoverned()).toBe(true));
  it('reports every resource for scheduled link checking',()=>expect(resourceHealthReport().length).toBeGreaterThanOrEqual(10));
});
