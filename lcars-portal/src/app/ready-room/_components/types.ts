export type Domain = 'attend' | 'decompose';

export function isDomain(value: string | null): value is Domain {
  return value === 'attend' || value === 'decompose';
}

export const EYEBROW: Record<Domain, string> = {
  attend: 'Ready Room · What needs you',
  decompose: 'Ready Room · Break it down',
};
