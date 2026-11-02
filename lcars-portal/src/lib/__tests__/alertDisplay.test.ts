import { describe, it, expect } from 'vitest';
import { displayHeadline, tidyCase } from '@/lib/alertDisplay';

describe('displayHeadline', () => {
  it('splits a WA DFES headline into title and subtitle and drops the CAD id', () => {
    expect(displayHeadline('BUSHFIRE (LAKE ARGYLE, SHIRE OF WYNDHAM-EAST KIMBERLEY, KIMBERLEY, CAD-ID: 828476)')).toEqual({
      title: 'Bushfire — Lake Argyle',
      subtitle: 'Shire of Wyndham-East Kimberley · Kimberley',
    });
  });

  it('title-cases an all-caps headline and leaves mixed case alone', () => {
    expect(displayHeadline('MOUNT BARKER : BURN OFF').title).toBe('Mount Barker : Burn Off');
    expect(displayHeadline('Moderate Flood Warning for the Barcoo River').title).toBe('Moderate Flood Warning for the Barcoo River');
    expect(tidyCase('Advice: Thunderstorm Asthma — Mallee District')).toBe('Advice: Thunderstorm Asthma — Mallee District');
  });

  it('does not touch a parenthesis that is not a CAD-ID block', () => {
    expect(displayHeadline('Warning for the Warrego River (QLD)')).toEqual({ title: 'Warning for the Warrego River (QLD)', subtitle: null });
  });
});
