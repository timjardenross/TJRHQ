// @vitest-environment jsdom
import { afterEach, describe, expect, it } from 'vitest';
import { render, screen, fireEvent, cleanup } from '@testing-library/react';
import { useState } from 'react';
import { DomainToggle, type DomainToggleOption } from '../DomainToggle';
// This repo has no global vitest setupFile registering jest-dom matchers
// (toHaveAttribute/toHaveFocus/toHaveTextContent) — import directly.
import '@testing-library/jest-dom/vitest';

// vitest.config.ts doesn't set `test.globals: true`, so @testing-library/
// react's own auto-cleanup (which hooks a global afterEach) never
// registers — without this, DOM from one it() block leaks into the next
// and role queries start matching duplicates across tests.
afterEach(cleanup);

// WORKBENCH-REVIEW.md H9/H12 (2026-07-18): none of the 7 prior forks had
// real keyboard behaviour — 5 "tablist" forks had only the ARIA labels,
// comms-workbench's role="radiogroup" fork had NO keyboard handler at all,
// and intelligence-workbench's inline version had no role/aria-selected
// whatsoever. These tests lock in the roving-tabindex + Arrow/Home/End
// behaviour the consolidated component actually implements, since axe-core
// alone verifies markup shape, not that the keys actually move focus and
// selection. No @testing-library/user-event in this repo — fireEvent.keyDown
// is the direct equivalent here.

const OPTIONS: DomainToggleOption<'a' | 'b' | 'c'>[] = [
  { key: 'a', label: 'Alpha' },
  { key: 'b', label: 'Bravo' },
  { key: 'c', label: 'Charlie', badge: 2 },
];

function Harness({ initial = 'a' as 'a' | 'b' | 'c' }) {
  const [value, setValue] = useState<'a' | 'b' | 'c'>(initial);
  return <DomainToggle value={value} onChange={setValue} options={OPTIONS} ariaLabel="Test domains" />;
}

describe('DomainToggle — WAI-ARIA APG tablist behaviour', () => {
  it('renders one role="tab" per option with only the active tab in the tab order', () => {
    render(<Harness />);
    const tabs = screen.getAllByRole('tab');
    expect(tabs).toHaveLength(3);
    expect(tabs[0]).toHaveAttribute('aria-selected', 'true');
    expect(tabs[0]).toHaveAttribute('tabIndex', '0');
    expect(tabs[1]).toHaveAttribute('aria-selected', 'false');
    expect(tabs[1]).toHaveAttribute('tabIndex', '-1');
    expect(tabs[2]).toHaveAttribute('tabIndex', '-1');
  });

  it('clicking a tab selects it', () => {
    render(<Harness />);
    fireEvent.click(screen.getByRole('tab', { name: /Bravo/ }));
    expect(screen.getByRole('tab', { name: /Bravo/ })).toHaveAttribute('aria-selected', 'true');
    expect(screen.getByRole('tab', { name: /Alpha/ })).toHaveAttribute('aria-selected', 'false');
  });

  it('ArrowRight moves selection and focus to the next tab, wrapping past the end', () => {
    render(<Harness />);
    const tablist = screen.getByRole('tablist');
    fireEvent.keyDown(tablist, { key: 'ArrowRight' });
    expect(screen.getByRole('tab', { name: /Bravo/ })).toHaveAttribute('aria-selected', 'true');
    expect(screen.getByRole('tab', { name: /Bravo/ })).toHaveFocus();

    fireEvent.keyDown(tablist, { key: 'ArrowRight' });
    fireEvent.keyDown(tablist, { key: 'ArrowRight' });
    expect(screen.getByRole('tab', { name: /Alpha/ })).toHaveAttribute('aria-selected', 'true');
  });

  it('ArrowLeft moves selection and focus to the previous tab, wrapping before the start', () => {
    render(<Harness />);
    const tablist = screen.getByRole('tablist');
    fireEvent.keyDown(tablist, { key: 'ArrowLeft' });
    expect(screen.getByRole('tab', { name: /Charlie/ })).toHaveAttribute('aria-selected', 'true');
    expect(screen.getByRole('tab', { name: /Charlie/ })).toHaveFocus();
  });

  it('Home jumps to the first tab and End jumps to the last', () => {
    render(<Harness initial="b" />);
    const tablist = screen.getByRole('tablist');
    fireEvent.keyDown(tablist, { key: 'End' });
    expect(screen.getByRole('tab', { name: /Charlie/ })).toHaveAttribute('aria-selected', 'true');

    fireEvent.keyDown(tablist, { key: 'Home' });
    expect(screen.getByRole('tab', { name: /Alpha/ })).toHaveAttribute('aria-selected', 'true');
  });

  it('renders the optional badge only when a value is present', () => {
    render(<Harness />);
    expect(screen.getByRole('tab', { name: /Charlie/ })).toHaveTextContent('2');
    expect(screen.getByRole('tab', { name: 'Alpha' })).toHaveTextContent('Alpha');
  });
});
