import { practiceLibrary } from './pain-recovery-practice-library';
import { resourceLibrary } from './pain-recovery-resource-library';

export type AuthoredGuidance = {
  message: string;
  next_action: string;
  choices: string[];
  action_type: 'continue'|'make_smaller'|'move_later'|'pause'|'reflect'|'safety_card';
  safety_instruction: 'none'|'show_card';
  practice: { title: string; duration: string; steps: string[]; revisit: string } | null;
  resources: { title: string; source: string; region: string; kind: string; url: string; why: string }[];
};

export type WholePersonContext = { request?: string; colour?: string; stage?: string; morning?: Record<string, string | null>; recipe?: { domain?: string; ingredient?: string; direction?: string }[] };

export function selectRecoveryDomain(context: WholePersonContext): 'biological'|'emotional'|'cognitive'|'social'|'environmental' {
  const text = [context.request, context.morning?.energy, context.morning?.sleep, context.morning?.mind, context.morning?.connection, context.morning?.setting].filter(Boolean).join(' ').toLowerCase();
  const recipe = context.recipe ?? [];
  const active = recipe.find((item) => item.direction === 'high' && item.domain);
  if (active?.domain && ['biological','emotional','cognitive','social','environmental'].includes(active.domain)) return active.domain as 'biological'|'emotional'|'cognitive'|'social'|'environmental';
  if (/alone|isolat|connection|person|message/.test(text)) return 'social';
  if (/thought|mind|fear|worry|busy|predict/.test(text)) return 'cognitive';
  if (/stress|brac|alarm|emotion/.test(text)) return 'emotional';
  if (/room|setting|pressure|demand|task|overwhelm/.test(text)) return 'environmental';
  return 'biological';
}

/** Phase 1's deterministic, no-AI guide. It must remain useful when consent
 * is declined, the router is unavailable, or the person has no energy. */
export function authoredGuidance(request = '', colour?: string, stage?: string, context: WholePersonContext = {}): AuthoredGuidance {
  const text = request.toLowerCase();
  if (/new|sudden|progressive|concerning|numb|weakness|bladder|bowel|chest|breath/.test(text)) {
    return { message: 'Pause here and use your agreed safety pathway.', next_action: 'Open the safety card and follow its instructions; the Studio will not judge the symptom.', choices: [], action_type: 'safety_card', safety_instruction: 'show_card', practice: null, resources: [] };
  }
  const low = /low|tired|overwhelm|too much|not possible|smaller/.test(text) || colour === 'Amber' || colour === 'Red' || stage === 'deferred';
  const domain = selectRecoveryDomain({ ...context, request, colour, stage });
  const practiceId = domain === 'social' ? 'reconnect' : domain === 'cognitive' ? 'three-cs' : domain === 'emotional' ? 'settle' : domain === 'environmental' ? (low ? 'reduce-load' : 'change-setting') : (low ? 'reduce-load' : 'valued-action');
  const practice = practiceLibrary.find((item) => item.id === practiceId)!;
  const resource = domain === 'social' ? resourceLibrary.find((item) => item.id === 'global-living')! : domain === 'biological' ? resourceLibrary.find((item) => item.id === 'au-pacing')! : resourceLibrary.find((item) => item.id === 'au-self-care')!;
  return {
    message: low ? `The ${domain} part of today is the best place to make the next step easier.` : `The ${domain} part of today is the best place to protect one small piece of life.`,
    next_action: low ? 'Choose one non-essential demand to remove, shorten, delegate, or move later.' : 'Choose the smallest version of the thing that matters today and set a stopping point before you begin.',
    choices: ['Make it smaller', 'Move it later', 'Choose a different route'], action_type: low ? 'make_smaller' : 'continue', safety_instruction: 'none',
    practice: { title: practice.title, duration: practice.duration, steps: [...practice.steps], revisit: practice.revisit },
    resources: [{ title: resource.title, source: resource.source, region: resource.region, kind: resource.kind, url: resource.url, why: resource.use }]
  };
}
