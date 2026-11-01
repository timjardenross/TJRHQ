// @vitest-environment jsdom
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import { Button } from '../Button';

describe('Button variants (auth-screen styles)', () => {
  afterEach(cleanup);

  it('caps adds the uppercase wide-tracked bold label', () => {
    render(<Button caps>Access Bridge</Button>);
    const cls = screen.getByRole('button').className;
    expect(cls).toMatch(/\buppercase\b/);
    expect(cls).toMatch(/tracking-\[0\.2em\]/);
    expect(cls).toMatch(/\bfont-bold\b/);
  });

  // Tailwind orders conflicting utilities by its own stylesheet, not by class-attribute
  // order, so a second weight/opacity class silently wins. Guard against emitting two.
  it.each([
    ['primary caps', { caps: true }],
    ['link', { variant: 'link' as const }],
    ['secondary', { variant: 'secondary' as const }],
  ])('%s emits exactly one font-weight and one disabled-opacity class', (_n, props) => {
    render(<Button {...props}>x</Button>);
    const cls = screen.getByRole('button').className.split(/\s+/);
    expect(cls.filter((c) => /^font-(normal|medium|semibold|bold)$/.test(c))).toHaveLength(1);
    expect(cls.filter((c) => /^disabled:opacity-/.test(c))).toHaveLength(1);
  });

  it('caps is bold, link is normal weight with 0.4 disabled opacity', () => {
    render(<><Button caps>a</Button><Button variant="link">b</Button></>);
    const [a, b] = screen.getAllByRole('button').map((e) => e.className);
    expect(a).toMatch(/\bfont-bold\b/);
    expect(b).toMatch(/\bfont-normal\b/);
    expect(b).toMatch(/disabled:opacity-40/);
  });

  it('fullWidth fills the container', () => {
    render(<Button fullWidth>Send</Button>);
    expect(screen.getByRole('button').className).toMatch(/\bw-full\b/);
  });

  it('link variant is muted, underlined and unpadded, with no filled background', () => {
    render(<Button variant="link">Forgot password?</Button>);
    const cls = screen.getByRole('button').className;
    expect(cls).toMatch(/\bunderline\b/);
    expect(cls).toMatch(/text-wb-ink2/);
    expect(cls).not.toMatch(/\bpx-\d/);
    expect(cls).not.toMatch(/\bpy-\d/);
    expect(cls).not.toMatch(/bg-wb-sage-deep/);
  });

  it('keeps type, disabled and aria-busy passing through, and defaults to type=button', () => {
    render(<Button type="submit" disabled aria-busy="true">Go</Button>);
    const b = screen.getByRole('button');
    expect(b.getAttribute('type')).toBe('submit');
    expect(b.hasAttribute('disabled')).toBe(true);
    expect(b.getAttribute('aria-busy')).toBe('true');
    cleanup();
    render(<Button>Plain</Button>);
    expect(screen.getByRole('button').getAttribute('type')).toBe('button');
  });

  it('the plain variants are unchanged (no caps, no full width)', () => {
    render(<Button variant="secondary">Cancel</Button>);
    const cls = screen.getByRole('button').className;
    expect(cls).not.toMatch(/uppercase/);
    expect(cls).not.toMatch(/\bw-full\b/);
  });
});
