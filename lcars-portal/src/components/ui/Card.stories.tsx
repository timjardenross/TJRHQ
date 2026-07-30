import type { Meta, StoryObj } from '@storybook/nextjs-vite';
import { Card } from './Card';
import { Button } from './Button';

const meta: Meta<typeof Card> = {
  title: 'TJR Design System/Card',
  component: Card,
  argTypes: {
    variant: { control: 'select', options: ['elevated', 'outlined'] },
  },
};
export default meta;

type Story = StoryObj<typeof Card>;

export const Elevated: Story = {
  args: { title: 'Pipeline', variant: 'elevated', children: 'Card body content goes here.' },
};

export const Outlined: Story = {
  args: { title: 'Pipeline', variant: 'outlined', children: 'Card body content goes here.' },
};

export const WithAction: Story = {
  render: () => (
    <Card title="Approval gate">
      <p className="mb-4 text-[13px] text-wb-ink2">3 of 4 QA checks passed.</p>
      <Button variant="primary">Pass remaining gate</Button>
    </Card>
  ),
};
