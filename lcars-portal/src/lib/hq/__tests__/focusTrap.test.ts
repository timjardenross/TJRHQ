// @vitest-environment jsdom
import { describe, expect, it } from 'vitest';
import { trapTab } from '../focusTrap';

function setup() {
  document.body.innerHTML = '<button id="outside">out</button><div id="dlg"><button id="a">a</button><textarea id="b"></textarea><button id="c" disabled>c</button><button id="d">d</button></div>';
  return { dlg: document.getElementById('dlg')!, a: document.getElementById('a')!, d: document.getElementById('d')!, outside: document.getElementById('outside')! };
}
const key = (shiftKey = false) => { const ev = { key: 'Tab', shiftKey, prevented: false, preventDefault() { this.prevented = true; } }; return ev; };

describe('dialog focus trap', () => {
  it('wraps forward from the last control to the first (skipping disabled)', () => {
    const { dlg, a, d } = setup(); d.focus();
    const ev = key(); trapTab(ev, dlg, document.activeElement);
    expect(ev.prevented).toBe(true);
    expect(document.activeElement).toBe(a);
  });
  it('wraps backward from the first control to the last', () => {
    const { dlg, a, d } = setup(); a.focus();
    const ev = key(true); trapTab(ev, dlg, document.activeElement);
    expect(ev.prevented).toBe(true);
    expect(document.activeElement).toBe(d);
  });
  it('leaves Tab alone in the middle of the dialog', () => {
    const { dlg } = setup(); document.getElementById('b')!.focus();
    const ev = key(); trapTab(ev, dlg, document.activeElement);
    expect(ev.prevented).toBe(false);
  });
  it('pulls focus back in if it escaped the dialog', () => {
    const { dlg, a, outside } = setup(); outside.focus();
    const ev = key(); trapTab(ev, dlg, document.activeElement);
    expect(ev.prevented).toBe(true);
    expect(document.activeElement).toBe(a);
  });
  it('ignores other keys', () => {
    const { dlg } = setup();
    const ev = { key: 'Enter', shiftKey: false, prevented: false, preventDefault() { this.prevented = true; } };
    trapTab(ev, dlg, document.activeElement);
    expect(ev.prevented).toBe(false);
  });
});
