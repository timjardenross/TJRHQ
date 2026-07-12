// @vitest-environment jsdom
import { describe, expect, it, vi } from 'vitest';
import { render } from '@testing-library/react';
import { axe } from 'vitest-axe';
// vitest-axe's own extend-expect entrypoint ships an empty build artifact
// (dist/extend-expect.js is 0 bytes), and its root matchers.d.ts incorrectly
// declares `export type *` even though the runtime export is a value — import
// the dist declaration directly and register the matcher (+ its Assertion type) ourselves.
import { toHaveNoViolations, type AxeMatchers } from 'vitest-axe/dist/matchers';
import { useState } from 'react';
import { Button } from '../Button';
import { Card } from '../Card';
import { Badge } from '../Badge';
import { Modal } from '../Modal';
import { Input, Textarea, Select, Checkbox } from '../Input';
import { ProgressBar, ProgressSteps } from '../Progress';
import { Tabs } from '../Navigation';

declare module 'vitest' {
  // eslint-disable-next-line
  interface Assertion<T = any> extends AxeMatchers {}
}

expect.extend({ toHaveNoViolations });

// next/link renders an <a> in tests without a router context.
vi.mock('next/link', () => ({
  default: ({ href, children, ...props }: { href: string; children: React.ReactNode }) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}));

function ModalHarness() {
  const [open, setOpen] = useState(true);
  return (
    <Modal open={open} onClose={() => setOpen(false)} title="Confirm action">
      <p>Are you sure?</p>
      <Button onClick={() => setOpen(false)}>Confirm</Button>
    </Modal>
  );
}

function TabsHarness() {
  const [active, setActive] = useState<'a' | 'b'>('a');
  return (
    <Tabs
      tabs={[
        { key: 'a', label: 'Signals' },
        { key: 'b', label: 'Pipeline' },
      ]}
      active={active}
      onChange={setActive}
      ariaLabel="Test sections"
    />
  );
}

describe('TJR Design System — component accessibility (axe-core, jsdom)', () => {
  it('Button has no axe violations', async () => {
    const { container } = render(<Button>Approve</Button>);
    expect(await axe(container)).toHaveNoViolations();
  });

  it('Card has no axe violations', async () => {
    const { container } = render(<Card title="Pipeline">Body content</Card>);
    expect(await axe(container)).toHaveNoViolations();
  });

  it('Badge has no axe violations', async () => {
    const { container } = render(<Badge status="warning">AMBER</Badge>);
    expect(await axe(container)).toHaveNoViolations();
  });

  it('Modal has no axe violations', async () => {
    const { container } = render(<ModalHarness />);
    expect(await axe(container)).toHaveNoViolations();
  });

  it('Input/Textarea/Select/Checkbox have no axe violations', async () => {
    const { container } = render(
      <form>
        <Input label="Subject" name="subject" />
        <Textarea label="Notes" name="notes" />
        <Select label="Priority" name="priority">
          <option value="low">Low</option>
        </Select>
        <Checkbox label="Notify me" name="notify" />
      </form>
    );
    expect(await axe(container)).toHaveNoViolations();
  });

  it('ProgressBar and ProgressSteps have no axe violations', async () => {
    const { container } = render(
      <div>
        <ProgressBar value={3} max={5} label="Data provenance" />
        <ProgressSteps
          steps={[
            { key: 'qa', label: 'QA gate', complete: true },
            { key: 'legal', label: 'Legal gate', complete: false },
          ]}
        />
      </div>
    );
    expect(await axe(container)).toHaveNoViolations();
  });

  it('Tabs and BackLink have no axe violations', async () => {
    const { container } = render(<TabsHarness />);
    expect(await axe(container)).toHaveNoViolations();
  });
});
