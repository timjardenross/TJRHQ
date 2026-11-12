import {describe,expect,it} from 'vitest';
import {isSafetyConcern,normaliseAction,stageForAction} from './pain-recovery-studio-guards';
describe('Pain Recovery Studio guardrails',()=>{
 it('flags safety language',()=>{expect(isSafetyConcern('a sudden change')).toBe(true);expect(isSafetyConcern('I want a smaller step')).toBe(false)});
 it('normalises unknown model actions',()=>{expect(normaliseAction('not-valid')).toBe('continue');expect(normaliseAction('make_smaller')).toBe('make_smaller')});
 it('forces safety actions into safety hold',()=>{expect(stageForAction('safety_card')).toBe('safety_hold');expect(stageForAction('reflect')).toBe('active')});
});