import {describe,expect,it} from 'vitest';
import {activityGuidanceBoundary,isActivityRoute} from './pain-recovery-activity-guidance';
describe('phase 7 activity boundaries',()=>{it('recognises only approved routes',()=>{expect(isActivityRoute('start')).toBe(true);expect(isActivityRoute('prescribe')).toBe(false)});it('keeps pause above activity coaching',()=>expect(activityGuidanceBoundary('pause')).toBe('safety_hold'));it('keeps Peter as exercise authority',()=>expect(activityGuidanceBoundary('start')).toBe('follow_peter_plan'));});
