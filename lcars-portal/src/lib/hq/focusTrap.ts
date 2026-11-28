// Keep Tab / Shift+Tab inside a modal dialog. Pure DOM logic so it can be
// tested without rendering React.
const FOCUSABLE = 'a[href],button:not([disabled]),input:not([disabled]),textarea:not([disabled]),select:not([disabled]),[tabindex]:not([tabindex="-1"])';

export function trapTab(e: { key: string; shiftKey: boolean; preventDefault: () => void }, container: HTMLElement | null, active: Element | null): void {
  if (e.key !== 'Tab' || !container) return;
  const items = Array.from(container.querySelectorAll<HTMLElement>(FOCUSABLE)).filter((el) => el.getAttribute('aria-hidden') !== 'true');
  if (items.length === 0) { e.preventDefault(); return; }
  const first = items[0];
  const last = items[items.length - 1];
  if (e.shiftKey && (active === first || !container.contains(active))) { e.preventDefault(); last.focus(); }
  else if (!e.shiftKey && (active === last || !container.contains(active))) { e.preventDefault(); first.focus(); }
}
