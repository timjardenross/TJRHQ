// Research is a type of work in HQ, backed by the existing mission mechanism.
//
// A research request is created as an ordinary mission (POST /api/missions, status "Idea")
// whose title starts with "Research:". HQ shows it in Work with the mission's real status.
//
// Honest status. No research runner is attached to missions: nothing reads a research mission
// and executes it (the one live mission dispatcher turns approved missions into code-change
// hand-offs, which is the wrong behaviour for research). So HQ states "Requested, not running"
// for a new request, and never states "running" or "findings ready" unless a person or a real
// executor has set a status that says so. When an executor is connected, only this mapping
// needs to learn the new statuses.
export const RESEARCH_PREFIX = 'Research:';
export const RESEARCH_NOT_RUNNING = 'Requested, not running';
export const RESEARCH_NO_RUNNER = 'No research runner is attached to missions, so nothing executes a research item yet. Progress and findings appear here only if someone records them on the mission.';

export const isResearchTitle = (title: string): boolean => title.trimStart().startsWith(RESEARCH_PREFIX);

export interface ResearchStatus {
  label: string;
  /** True only when something real says the research is executing. Always false today. */
  executing: boolean;
  tone: 'info' | 'amber' | 'green';
}

export function researchStatus(missionStatus: string): ResearchStatus {
  switch (missionStatus) {
    case 'Idea': return { label: RESEARCH_NOT_RUNNING, executing: false, tone: 'info' };
    case 'Blocked':
    case 'Requires Rework': return { label: `Blocked (${missionStatus})`, executing: false, tone: 'amber' };
    case 'Awaiting Number One Review':
    case 'Awaiting XO Approval':
    case 'Awaiting Captain Approval':
    case 'Validated': return { label: `Ready for review (${missionStatus})`, executing: false, tone: 'green' };
    case 'Closed':
    case 'Archived': return { label: 'Done', executing: false, tone: 'green' };
    // Any other recorded status is shown verbatim, never reinterpreted as "running".
    default: return { label: `Status recorded: ${missionStatus}`, executing: false, tone: 'info' };
  }
}

export const researchTitle = (question: string): string => `${RESEARCH_PREFIX} ${question.trim()}`.slice(0, 200);
