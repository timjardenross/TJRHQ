import type { Meta, StoryObj } from '@storybook/nextjs-vite';
import { ProgressBar, ProgressSteps } from './Progress';

const meta: Meta = {
  title: 'TJR Design System/Progress',
};
export default meta;

type Story = StoryObj;

export const Bar: Story = {
  render: () => <ProgressBar value={3} max={5} label="Data provenance" />,
};

export const MultipleBars: Story = {
  render: () => (
    <div className="flex flex-col gap-1.5">
      <ProgressBar value={4} max={5} label="Data provenance" />
      <ProgressBar value={2} max={5} label="Stakeholder impact" />
      <ProgressBar value={5} max={5} label="Recovery difficulty" />
    </div>
  ),
};

export const Steps: Story = {
  render: () => (
    <ProgressSteps
      steps={[
        { key: 'qa', label: 'QA gate', complete: true },
        { key: 'legal', label: 'Legal gate', complete: true },
        { key: 'exec', label: 'Executive gate', complete: false },
      ]}
    />
  ),
};
