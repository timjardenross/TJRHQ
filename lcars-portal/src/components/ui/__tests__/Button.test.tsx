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
