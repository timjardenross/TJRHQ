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

/** Phase 1's deterministic, no-AI guide. It must remain useful when consent
 * is declined, the router is unavailable, or the person has no energy. */
export function authoredGuidance(request = '', colour?: string, stage?: string): AuthoredGuidance {
  const text = request.toLowerCase();
  if (/new|sudden|progressive|concerning|numb|weakness|bladder|bowel|chest|breath/.test(text)) {
    return { message: 'Pause here and use your agreed safety pathway.', next_action: 'Open the safety card and follow its instructions; the Studio will not judge the symptom.', choices: [], action_type: 'safety_card', safety_instruction: 'show_card', practice: null, resources: [] };
  }
  const low = /low|tired|overwhelm|too much|not possible|smaller/.test(text) || colour === 'Amber' || colour === 'Red' || stage === 'deferred';
  const practice = low ? practiceLibrary.find((item) => item.id === 'reduce-load')! : practiceLibrary.find((item) => item.id === 'valued-action')!;
  const resource = low ? resourceLibrary.find((item) => item.id === 'au-pacing')! : resourceLibrary.find((item) => item.id === 'au-self-care')!;
  return {
    message: low ? 'Let’s reduce the demand while keeping one useful thread of the day.' : 'Let’s protect one small piece of life without turning it into a test.',
    next_action: low ? 'Choose one non-essential demand to remove, shorten, delegate, or move later.' : 'Choose the smallest version of the thing that matters today and set a stopping point before you begin.',
    choices: ['Make it smaller', 'Move it later', 'Choose a different route'], action_type: low ? 'make_smaller' : 'continue', safety_instruction: 'none',
    practice: { title: practice.title, duration: practice.duration, steps: [...practice.steps], revisit: practice.revisit },
    resources: [{ title: resource.title, source: resource.source, region: resource.region, kind: resource.kind, url: resource.url, why: resource.use }]
  };
}
