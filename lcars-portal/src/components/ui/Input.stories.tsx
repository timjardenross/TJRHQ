import type { Meta, StoryObj } from '@storybook/nextjs-vite';
import { Input, Textarea, Select, Checkbox } from './Input';

const meta: Meta = {
  title: 'TJR Design System/Input',
};
export default meta;

type Story = StoryObj;

export const TextField: Story = {
  render: () => <Input label="Subject" placeholder="Weekly update" />,
};

export const TextareaField: Story = {
  render: () => <Textarea label="Notes" hint="Optional, visible to reviewers." rows={3} />,
};

export const SelectField: Story = {
  render: () => (
    <Select label="Priority">
      <option value="low">Low</option>
      <option value="medium">Medium</option>
      <option value="high">High</option>
    </Select>
  ),
};

export const CheckboxField: Story = {
  render: () => <Checkbox label="Notify reviewer on approval" />,
};

export const FormLayout: Story = {
  render: () => (
    <form className="flex max-w-sm flex-col gap-4">
      <Input label="Subject" placeholder="Weekly update" />
      <Select label="Priority">
        <option value="low">Low</option>
        <option value="high">High</option>
      </Select>
      <Textarea label="Notes" rows={3} />
      <Checkbox label="Notify reviewer on approval" />
    </form>
  ),
};
