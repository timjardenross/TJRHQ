import type { Preview } from '@storybook/nextjs-vite'
import React from 'react'
import '../src/app/globals.css'

const preview: Preview = {
  parameters: {
    controls: {
      matchers: {
       color: /(background|color)$/i,
       date: /Date$/i,
      },
    },
  },
  // Stories render on the TJR Design System's own wb-bg surface, not the
  // LCARS app chrome — globals.css sets that on <body>, so override locally.
  decorators: [
    (Story) => (
      <div className="min-h-[200px] bg-wb-bg p-8 font-sans text-wb-ink antialiased">
        <Story />
      </div>
    ),
  ],
};

export default preview;