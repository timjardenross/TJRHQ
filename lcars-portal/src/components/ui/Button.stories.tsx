import type { Meta, StoryObj } from '@storybook/nextjs-vite';
import { Button } from './Button';

const meta: Meta<typeof Button> = {
  title: 'TJR Design System/Button',
  component: Button,
  argTypes: {
    variant: { control: 'select', options: ['primary', 'secondary', 'danger', 'ghost', 'link'] },
    size: { control: 'select', options: ['sm', 'md'] },
  },
};
export default meta;

type Story = StoryObj<typeof Button>;

export const Primary: Story = { args: { variant: 'primary', children: 'Approve' } };
export const Secondary: Story = { args: { variant: 'secondary', children: 'Cancel' } };
export const Danger: Story = { args: { variant: 'danger', children: 'Reject' } };
export const Ghost: Story = { args: { variant: 'ghost', children: 'Skip' } };
export const Small: Story = { args: { variant: 'primary', size: 'sm', children: 'Approve' } };
export const Caps: Story = { args: { variant: 'primary', caps: true, children: 'Access Bridge' } };
export const FullWidthCaps: Story = {
  args: { variant: 'primary', caps: true, fullWidth: true, children: 'Send Access Link' },
  decorators: [(Story) => <div className="w-80"><Story /></div>],
};
export const Link: Story = { args: { variant: 'link', children: 'Forgot password?' } };
export const Disabled: Story = { args: { variant: 'primary', children: 'Approve', disabled: true } };

export const AllVariants: Story = {
  render: () => (
    <div className="flex flex-wrap items-center gap-3">
      <Button variant="primary">Primary</Button>
      <Button variant="secondary">Secondary</Button>
      <Button variant="danger">Danger</Button>
      <Button variant="ghost">Ghost</Button>
      <Button variant="link">Link</Button>
      <Button variant="primary" caps>Caps</Button>
    </div>
  ),
};
