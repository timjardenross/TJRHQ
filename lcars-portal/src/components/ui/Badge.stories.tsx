import type { Meta, StoryObj } from '@storybook/nextjs-vite';
import { Badge, riskToStatus } from './Badge';

const meta: Meta<typeof Badge> = {
  title: 'TJR Design System/Badge',
  component: Badge,
  argTypes: {
    status: { control: 'select', options: ['success', 'warning', 'error', 'info', 'neutral'] },
  },
};
export default meta;

type Story = StoryObj<typeof Badge>;

export const Success: Story = { args: { status: 'success', children: 'GREEN' } };
export const Warning: Story = { args: { status: 'warning', children: 'AMBER' } };
export const ErrorStatus: Story = { args: { status: 'error', children: 'RED' } };
export const Info: Story = { args: { status: 'info', children: 'INFO' } };
export const Neutral: Story = { args: { status: 'neutral', children: '—' } };

export const FromRiskValue: Story = {
  render: () => (
    <div className="flex gap-2">
      {['RED', 'AMBER', 'GREEN', 'UNKNOWN'].map((risk) => (
        <Badge key={risk} status={riskToStatus(risk)}>
          {risk}
        </Badge>
      ))}
    </div>
  ),
};
