import type { Meta, StoryObj } from '@storybook/nextjs-vite';
import { useState } from 'react';
import { Tabs, BackLink } from './Navigation';

const meta: Meta = {
  title: 'TJR Design System/Navigation',
};
export default meta;

type Story = StoryObj;

function TabsHarness() {
  const [active, setActive] = useState<'signals' | 'pipeline' | 'portfolio'>('signals');
  return (
    <Tabs
      tabs={[
        { key: 'signals', label: 'Signals' },
        { key: 'pipeline', label: 'Pipeline' },
        { key: 'portfolio', label: 'Portfolio' },
      ]}
      active={active}
      onChange={setActive}
      ariaLabel="Communications Workbench sections"
    />
  );
}

export const TabNav: Story = { render: () => <TabsHarness /> };

export const BackLinkExample: Story = {
  render: () => <BackLink href="/intelligence-workbench" label="Back to workbench" />,
};
