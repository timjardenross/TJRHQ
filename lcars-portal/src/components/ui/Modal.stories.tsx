import type { Meta, StoryObj } from '@storybook/nextjs-vite';
import { useState } from 'react';
import { Modal } from './Modal';
import { Button } from './Button';

const meta: Meta<typeof Modal> = {
  title: 'TJR Design System/Modal',
  component: Modal,
};
export default meta;

type Story = StoryObj<typeof Modal>;

function DialogHarness() {
  const [open, setOpen] = useState(true);
  return (
    <>
      <Button onClick={() => setOpen(true)}>Open dialog</Button>
      <Modal open={open} onClose={() => setOpen(false)} title="Confirm approval" variant="dialog">
        <p className="mb-4 text-[13px] text-wb-ink2">
          This will pass the QA gate and notify the reviewer. This cannot be undone.
        </p>
        <div className="flex justify-end gap-2">
          <Button variant="secondary" onClick={() => setOpen(false)}>
            Cancel
          </Button>
          <Button variant="primary" onClick={() => setOpen(false)}>
            Confirm
          </Button>
        </div>
      </Modal>
    </>
  );
}

function PreviewHarness() {
  const [open, setOpen] = useState(true);
  return (
    <>
      <Button onClick={() => setOpen(true)}>Preview content</Button>
      <Modal open={open} onClose={() => setOpen(false)} title="Draft preview" variant="preview">
        <p className="text-[13px] text-wb-ink2">Wider layout for previewing generated content before it ships.</p>
      </Modal>
    </>
  );
}

export const Dialog: Story = { render: () => <DialogHarness /> };
export const Preview: Story = { render: () => <PreviewHarness /> };
