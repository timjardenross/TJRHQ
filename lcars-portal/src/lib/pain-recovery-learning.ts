export type LearningSignal = 'helped'|'harder'|'preserved'|'cost_more'|'repeat'|string;

export function tomorrowPrompt(note?: string|null) {
  const text = (note || '').toLowerCase();
  if (text.includes('cost more') || text.includes('harder')) return 'Tomorrow can start lighter. What is the smallest useful version?';
  if (text.includes('protected') || text.includes('repeat')) return 'You have one ingredient worth carrying forward. Would you like to begin there?';
  if (text.includes('helped')) return 'Something helped yesterday. Would you like to use that as today’s starting point?';
  return 'Start with today, not catch-up. What would make the next step possible?';
}
