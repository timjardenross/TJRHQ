import type { Meta, StoryObj } from '@storybook/nextjs-vite';
import { BrandMark } from './BrandMark';
import { BrandWordmark, type WordmarkLayout } from './BrandWordmark';

// Visual baseline for the TJR HQ identity. Surfaces mirror HQ's real ones:
// dark chrome (--wb-bg / sidebar), the light Read-mode surface, and white.
const SURFACES = [
  { name: 'Dark chrome', bg: '#0B1E2E', surface: 'dark' as const },
  { name: 'Read mode (light)', bg: '#F4F0E8', surface: 'light' as const },
  { name: 'White', bg: '#FFFFFF', surface: 'light' as const },
];

function Marks() {
  return (
    <div className="space-y-4">
      {SURFACES.map((s) => (
        <div key={s.name} style={{ background: s.bg }} className="flex flex-wrap items-center gap-6 rounded-lg p-4">
          <span className="w-36 text-[12px]" style={{ color: s.surface === 'dark' ? '#B7C6D4' : '#4A5F75' }}>{s.name}</span>
          {[16, 24, 32, 36, 48, 64].map((n) => (
            <BrandMark key={n} surface={s.surface} size={n} />
          ))}
          <BrandMark surface={s.surface} mono size={48} />
        </div>
      ))}
    </div>
  );
}

function Wordmarks() {
  const layouts: WordmarkLayout[] = ['primary', 'horizontal', 'compact'];
  return (
    <div className="space-y-4">
      {SURFACES.map((s) => (
        <div key={s.name} style={{ background: s.bg }} className="space-y-4 rounded-lg p-4">
          {layouts.map((l) => (
            <div key={l}>
              <BrandWordmark layout={l} surface={s.surface} width={l === 'primary' ? 420 : l === 'horizontal' ? 260 : 140} />
            </div>
          ))}
          <BrandWordmark surface={s.surface} mono width={200} />
        </div>
      ))}
    </div>
  );
}

const meta: Meta = {
  title: 'TJR Design System/Brand',
  parameters: { layout: 'padded' },
};
export default meta;
type S = StoryObj;

export const Marks_AllSurfacesAndSizes: S = { render: () => <Marks /> };
export const Wordmarks_AllSurfaces: S = { render: () => <Wordmarks /> };
// In a link, as it will be used in Stage 2: the link carries the name, the
// mark is decorative.
export const InLink: S = {
  render: () => (
    <a href="/hub" aria-label="Workbenches home" className="inline-flex rounded-md focus-visible:outline focus-visible:outline-2">
      <BrandMark surface="dark" />
    </a>
  ),
  parameters: { backgrounds: { default: 'dark' } },
};
