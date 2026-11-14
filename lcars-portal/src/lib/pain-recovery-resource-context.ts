import type { RecoveryResource } from './pain-recovery-resource-library';

export type ResourceNeed = 'pace' | 'understand' | 'connect' | 'explore';
export const resourceNeeds: Array<{ id: ResourceNeed; label: string; description: string }> = [
  { id: 'pace', label: 'Make today more manageable', description: 'Pacing, planning and reducing the push-crash cycle.' },
  { id: 'understand', label: 'Understand pain care', description: 'Plain-language whole-person education.' },
  { id: 'connect', label: 'Feel less alone', description: 'Peer, community and lived-experience resources.' },
  { id: 'explore', label: 'Browse the library', description: 'See all approved resources.' },
];
const matches: Record<Exclude<ResourceNeed, 'explore'>, (resource: RecoveryResource) => boolean> = {
  pace: (resource) => resource.kind === 'pacing' || resource.domain === 'biological',
  understand: (resource) => resource.kind === 'education' || resource.domain === 'whole-person',
  connect: (resource) => resource.kind === 'support' || resource.domain === 'social',
};
export function resourcesForNeed(resources: RecoveryResource[], need: ResourceNeed): RecoveryResource[] {
  if (need === 'explore') return resources;
  const selected = resources.filter(matches[need]);
  return selected.length ? selected : resources;
}
export function contextualReason(resource: RecoveryResource, need: ResourceNeed): string {
  if (need !== 'explore' && matches[need](resource)) return resource.use;
  return `A broader ${resource.kind} resource if you want to explore beyond the first suggestion.`;
}
