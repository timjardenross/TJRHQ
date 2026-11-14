export type LearningSignal = 'helped'|'harder'|'preserved'|'cost_more'|'repeat'|string;
export type DayLearningRecord = { date:string; colour?:string|null; sleep?:string|null; energy?:string|null; demand?:string|null; valuedActivity?:string|null; actionStatus?:string|null; nextDayCost?:number|null; learningNote?:string|null };
export type LearningDecision = { id:string; date:string; decision:'use'|'different'|'modified'; note?:string };
export type WeeklySummary = { start:string; days:number; averageCost:number|null; completed:number; preserved:number };

export function normalizeCost(value: unknown): number|null {
  if (value === null || value === undefined || value === '' || value === 'none') return 0;
  const number = typeof value === 'number' ? value : Number(value);
  return Number.isFinite(number) && number >= 0 && number <= 3 ? Math.round(number) : null;
}

export function upsertLearningRecord(records: DayLearningRecord[], record: DayLearningRecord): DayLearningRecord[] {
  const next = records.filter(item => item.date !== record.date);
  return [...next, record].sort((a,b)=>a.date.localeCompare(b.date));
}

export function findSimilarDays(current: DayLearningRecord, records: DayLearningRecord[]): DayLearningRecord[] {
  return records.filter(item => item.date !== current.date).map(item => ({ item, score: [current.colour && item.colour === current.colour, current.sleep && item.sleep === current.sleep, current.energy && item.energy === current.energy, current.demand && item.demand === current.demand, current.valuedActivity && item.valuedActivity === current.valuedActivity].filter(Boolean).length })).filter(({score})=>score >= 2).sort((a,b)=>b.score-a.score).map(({item})=>item).slice(0,5);
}

export function buildLearningSuggestion(days: DayLearningRecord[]): { message:string; confidence:'low'|'medium'|'high' }|null {
  if (!days.length) return null;
  const useful = days.filter(day => day.learningNote || day.actionStatus === 'completed');
  if (!useful.length) return null;
  const confidence = useful.length >= 6 ? 'high' : useful.length >= 3 ? 'medium' : 'low';
  const activity = useful.find(day => day.valuedActivity)?.valuedActivity;
  return { message: activity ? `An observed pattern from a similar day includes ${activity}. You can try a smaller version, or choose something else.` : 'There is an observed pattern from a similar day. Use it as an option, not a rule.', confidence };
}

export function saveLearningDecision(decisions: LearningDecision[], decision: LearningDecision): LearningDecision[] { return [...decisions.filter(item=>item.id!==decision.id), decision]; }
export function summarizeWeek(records: DayLearningRecord[], start:string): WeeklySummary { const end=new Date(`${start}T00:00:00Z`); end.setUTCDate(end.getUTCDate()+7); const inWeek=records.filter(r=>r.date>=start&&r.date<end.toISOString().slice(0,10)); const costs=inWeek.map(r=>r.nextDayCost).filter((v):v is number=>typeof v==='number'); return {start,days:inWeek.length,averageCost:costs.length?costs.reduce((a,b)=>a+b,0)/costs.length:null,completed:inWeek.filter(r=>r.actionStatus==='completed').length,preserved:inWeek.filter(r=>r.learningNote?.toLowerCase().includes('protected')||r.learningNote?.toLowerCase().includes('preserved')).length}; }
export function compareWeeks(current:WeeklySummary, previous:WeeklySummary){ return {costChange:current.averageCost===null||previous.averageCost===null?null:current.averageCost-previous.averageCost,completionChange:current.completed-previous.completed}; }
export function exportLearningData(records:DayLearningRecord[], decisions:LearningDecision[]){ return JSON.stringify({version:1,exportedAt:new Date().toISOString(),records,decisions}); }

export function tomorrowPrompt(note?: string|null) {
  const text = (note || '').toLowerCase();
  if (text.includes('cost more') || text.includes('harder')) return 'Tomorrow can start lighter. What is the smallest useful version?';
  if (text.includes('protected') || text.includes('repeat')) return 'You have one ingredient worth carrying forward. Would you like to begin there?';
  if (text.includes('helped')) return 'Something helped yesterday. Would you like to use that as today’s starting point?';
  return 'Start with today, not catch-up. What would make the next step possible?';
}
