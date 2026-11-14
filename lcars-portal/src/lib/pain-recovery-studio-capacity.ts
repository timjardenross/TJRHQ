export type CapacityInput = { sleep?: string; energy?: string; demand?: string; yesterdayCost?: string; flare?: string };
export type CapacityColour = 'Green'|'Amber'|'Red';

/** R1: deterministic capacity only. Safety signals are handled separately. */
export function suggestCapacity(input: CapacityInput): CapacityColour {
  if (input.flare === 'yes') return 'Red';
  const triggers = [
    input.sleep === 'poor',
    input.energy === 'low',
    input.demand === 'heavy',
    input.yesterdayCost === 'high'
  ].filter(Boolean).length;
  return triggers >= 3 ? 'Red' : triggers >= 1 ? 'Amber' : 'Green';
}
