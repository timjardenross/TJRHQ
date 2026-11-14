export const ALLOWED_GUIDANCE_ACTIONS=['continue','make_smaller','move_later','pause','reflect','safety_card'] as const;
export type GuidanceAction=typeof ALLOWED_GUIDANCE_ACTIONS[number];
export function isSafetyConcern(value:string){return /new|sudden|progressive|concerning|different from usual|numb|weakness|bladder|bowel|chest pain|breath(?:ing)?|harming myself|harming someone/i.test(value);}
export function normaliseAction(value:unknown):GuidanceAction{return typeof value==='string'&& (ALLOWED_GUIDANCE_ACTIONS as readonly string[]).includes(value)?value as GuidanceAction:'continue';}
export function stageForAction(action:GuidanceAction|string){return action==='safety_card'?'safety_hold':'active';}
