export type Domain = 'do' | 'unstick';

export function isDomain(value: string | null): value is Domain {
  return value === 'do' || value === 'unstick';
}

export const EYEBROW: Record<Domain, string> = {
  do: 'Ready Room · What’s worth doing now',
  unstick: 'Ready Room · Help me start',
};
