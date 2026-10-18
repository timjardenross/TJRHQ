// @vitest-environment jsdom
import { afterEach, describe, expect, it } from 'vitest';
import { render, screen, cleanup } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import { BrandMark, brandMarkSrc } from '../BrandMark';
import { BrandWordmark, WORDMARK_MIN_WIDTH, brandWordmarkSrc } from '../BrandWordmark';

afterEach(cleanup);

describe('BrandMark', () => {
  it('is decorative by default: empty alt, no image role, name left to the parent link', () => {
    const { container } = render(
      <a href="/hub" aria-label="Workbenches home">
        <BrandMark />
      </a>,
    );
    const img = container.querySelector('img')!;
    expect(img).toHaveAttribute('alt', '');
    expect(screen.queryByRole('img')).toBeNull();
    expect(screen.getByRole('link', { name: 'Workbenches home' })).toBeInTheDocument();
  });

  it('exposes an accessible name only when a label is given', () => {
    render(<BrandMark label="TJR HQ" />);
    expect(screen.getByRole('img', { name: 'TJR HQ' })).toBeInTheDocument();
  });

  it('uses 36 px by default (the existing header slot) and rounds the tile, not the bare mark', () => {
    const { container, rerender } = render(<BrandMark />);
    const img = container.querySelector('img')!;
    expect(img).toHaveAttribute('width', '36');
    expect(img).toHaveAttribute('height', '36');
    expect(img.style.borderRadius).toBe('22%');
    rerender(<BrandMark mono />);
    expect(container.querySelector('img')!.style.borderRadius).toBe('');
  });

  it('picks the tile by surface: navy on light, inverted on dark', () => {
    expect(brandMarkSrc('light', false, 36)).toBe('/brand/hq-icon-light.svg');
    expect(brandMarkSrc('dark', false, 36)).toBe('/brand/hq-icon-dark.svg');
  });

  it('uses the heavier-stroke favicon cuts only at small sizes on light surfaces', () => {
    expect(brandMarkSrc('light', false, 16)).toBe('/brand/hq-favicon-16.svg');
    expect(brandMarkSrc('light', false, 32)).toBe('/brand/hq-favicon-32.svg');
    expect(brandMarkSrc('light', false, 33)).toBe('/brand/hq-icon-light.svg');
    expect(brandMarkSrc('dark', false, 16)).toBe('/brand/hq-icon-dark.svg');
  });

  it('maps monochrome to navy on light and white on dark', () => {
    expect(brandMarkSrc('light', true, 48)).toBe('/brand/hq-icon-mono-navy.svg');
    expect(brandMarkSrc('dark', true, 48)).toBe('/brand/hq-icon-mono-white.svg');
  });
});

describe('BrandWordmark', () => {
  it('is named "TJR HQ" by default and can be silenced when a sibling names it', () => {
    const { rerender } = render(<BrandWordmark />);
    expect(screen.getByRole('img', { name: 'TJR HQ' })).toBeInTheDocument();
    rerender(<BrandWordmark label="" />);
    expect(screen.queryByRole('img')).toBeNull();
  });

  it('never renders narrower than the layout minimum (primary keeps its descriptor at 12 px or more)', () => {
    const { container } = render(<BrandWordmark layout="primary" width={100} />);
    expect(Number(container.querySelector('img')!.getAttribute('width'))).toBe(WORDMARK_MIN_WIDTH.primary);
    expect(WORDMARK_MIN_WIDTH.primary).toBe(310);
  });

  it('keeps the natural aspect ratio', () => {
    const { container } = render(<BrandWordmark layout="horizontal" width={686} />);
    const img = container.querySelector('img')!;
    expect(Number(img.getAttribute('width')) / Number(img.getAttribute('height'))).toBeCloseTo(686.32 / 180, 1);
  });

  it('mono is a horizontal-footprint lockup: its own file, its own aspect, and the type rejects other layouts', () => {
    const { container } = render(<BrandWordmark mono width={582} />);
    const img = container.querySelector('img')!;
    expect(Number(img.getAttribute('width')) / Number(img.getAttribute('height'))).toBeCloseTo(582.88 / 180, 1);
    // @ts-expect-error the component props reject mono with a non-horizontal layout
    const bad = <BrandWordmark layout="compact" mono />;
    expect(bad).toBeTruthy();
  });

  it('maps layout, surface and mono to the shipped files', () => {
    expect(brandWordmarkSrc('primary', 'light', false)).toBe('/brand/hq-wordmark-primary-light.svg');
    expect(brandWordmarkSrc('compact', 'dark', false)).toBe('/brand/hq-wordmark-compact-dark.svg');
    expect(brandWordmarkSrc('horizontal', 'dark', true)).toBe('/brand/hq-wordmark-mono-white.svg');
  });
});
