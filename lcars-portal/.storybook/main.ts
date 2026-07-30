import type { StorybookConfig } from '@storybook/nextjs-vite';

const config: StorybookConfig = {
  "stories": [
    "../src/**/*.mdx",
    "../src/**/*.stories.@(js|jsx|mjs|ts|tsx)"
  ],
  "addons": [
    "@storybook/addon-a11y",
    "@storybook/addon-docs",
    "@storybook/addon-mcp"
  ],
  "framework": "@storybook/nextjs-vite",
  "staticDirs": [
    "../public"
  ],
  // Tailwind's content scanner treats the whole src/ tree as candidate class
  // source, including non-UI files. src/lib/ai-actions.ts has a regex literal
  // `/[-:.TZ]/g` that gets misread as an arbitrary-value class `[-:.TZ]`, which
  // lightningcss's minifier can't parse. It's inert (never a real class), so
  // skip lightningcss minification for the Storybook build rather than touch
  // unrelated app code.
  viteFinal: async (viteConfig) => {
    viteConfig.build = { ...viteConfig.build, cssMinify: 'esbuild' };
    return viteConfig;
  },
};
export default config;