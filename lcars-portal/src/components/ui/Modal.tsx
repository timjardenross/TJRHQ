'use client';

import { ReactNode, useEffect, useRef } from 'react';

export type ModalVariant = 'dialog' | 'preview';

export interface ModalProps {
  open: boolean;
  onClose: () => void;
  title: string;
  variant?: ModalVariant;
  children: ReactNode;
}

/** TJR Design System — new primitive (no existing modal was found across the 3 audited sources). */
export function Modal({ open, onClose, title, variant = 'dialog', children }: ModalProps) {
  const panelRef = useRef<HTMLDivElement>(null);
  // WP3 defect #2: focus was falling back to <body> on Escape/close instead
  // of returning to whatever control opened the dialog. Capture
  // document.activeElement at the moment `open` flips true (that's still
  // the trigger button — this runs before the caller's own click handler
  // has moved focus anywhere else) and restore it once `open` flips back
  // to false, regardless of which path closed the dialog (Escape, backdrop
  // click, the X button, or a link inside the panel).
  const triggerRef = useRef<HTMLElement | null>(null);

  // Mission 7 §31 accessibility pass: Escape-to-close already existed, but
  // nothing kept Tab/Shift+Tab inside the dialog — every one of this
  // component's ~15 call sites let a keyboard/screen-reader user tab
  // straight out into the page behind the open modal, off-screen and
  // unannounced. Fixed once here rather than per call site.
  useEffect(() => {
    if (!open) return;
    function focusableEls(): HTMLElement[] {
      if (!panelRef.current) return [];
      return Array.from(
        panelRef.current.querySelectorAll<HTMLElement>(
          'a[href], button:not([disabled]), textarea:not([disabled]), input:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])',
        ),
      ).filter((el) => el.offsetParent !== null);
    }
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === 'Escape') {
        onClose();
        return;
      }
      if (e.key !== 'Tab') return;
      const els = focusableEls();
      if (els.length === 0) return;
      const first = els[0];
      const last = els[els.length - 1];
      const active = document.activeElement;
      if (e.shiftKey && active === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && active === last) {
        e.preventDefault();
        first.focus();
      } else if (!panelRef.current?.contains(active)) {
        // Focus somehow escaped the panel (e.g. programmatic focus() from
        // outside) — pull it back in rather than let Tab continue into
        // the page behind the modal.
        e.preventDefault();
        first.focus();
      }
    }
    document.addEventListener('keydown', onKeyDown);
    panelRef.current?.focus();
    return () => document.removeEventListener('keydown', onKeyDown);
  }, [open, onClose]);

  useEffect(() => {
    if (open) {
      triggerRef.current = document.activeElement as HTMLElement | null;
      return;
    }
    const trigger = triggerRef.current;
    triggerRef.current = null;
    // Only refocus an element still attached to the document — a trigger
    // that navigated away or unmounted while the dialog was open shouldn't
    // throw or silently no-op focus() on a detached node.
    if (trigger && document.contains(trigger)) {
      trigger.focus();
    }
  }, [open]);

  if (!open) return null;

  // Full literal sm: class strings (not sm:${...} concatenation) —
  // Tailwind's JIT scanner needs the complete class name present verbatim
  // in source to generate its CSS; a runtime-built "sm:" + variable string
  // would silently produce no CSS at all.
  const widthClass = variant === 'preview' ? 'sm:max-w-3xl' : 'sm:max-w-md';

  // max-h-[85vh] + flex-col + the inner overflow-y-auto wrapper (rather than
  // scrolling the whole panel) keep the title/close button fixed in place
  // while body content scrolls — without this, a panel taller than the
  // viewport (e.g. a draft plus AI review results plus a checklist) had no
  // way to reach content below the fold; the backdrop itself doesn't scroll.
  // 2026-08-09 mobile/iPad review (P3): centered-dialog-at-every-size
  // worked but didn't feel native on a phone. Below sm this now anchors
  // to the bottom edge, full width, rounded top corners only, taller
  // max-height (90dvh vs 85vh — more of the screen is genuinely available
  // once it's not floating with margin on all sides) — a sheet-like
  // presentation without adding swipe-to-dismiss gesture logic (real
  // touch-gesture work, out of scope for this pass). sm+ is completely
  // unchanged: centered, padded, original widthClass/85vh/rounded-lg.
  // WP3 defect #1: below `xl`, MobileCommandBar (components/MobileCommandBar.tsx)
  // is a fixed bottom nav at z-50, mounted *after* this dialog's own
  // WorkbenchShell sibling in the DOM (<QuickCapture/> then
  // <MobileCommandBar/>). At equal z-index, later-DOM wins paint order, so
  // the nav bar rendered on top of this sheet's own flush-bottom edge and
  // silently ate pointer events meant for whatever sat at the bottom of the
  // panel (e.g. QuickCapture's Capture submit button) — confirmed live at
  // 390px, had to force-click via JS to get past it. z-[60] guarantees this
  // dialog (and its backdrop) always sits above that nav regardless of DOM
  // order. The mobile sheet variant also sits flush against the physical
  // bottom edge (items-end, no bottom offset) so its own p-6 alone isn't
  // enough headroom on devices with a safe-area inset (notch/home
  // indicator) — bump bottom padding to clear it below `sm`, unchanged at
  // `sm`+ where the dialog is centered with margin on all sides already.
  return (
    <div className="fixed inset-0 z-[60] flex items-end justify-center bg-wb-ink/40 sm:items-center sm:p-4" onClick={onClose}>
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="tjr-modal-title"
        tabIndex={-1}
        className={`flex max-h-[90dvh] w-full flex-col rounded-t-2xl border border-wb-line bg-wb-surface p-6 pb-[max(1.5rem,calc(env(safe-area-inset-bottom)_+_1rem))] shadow-lg
          focus-visible:outline focus-visible:outline-2 focus-visible:outline-wb-sage-deep
          sm:max-h-[85vh] sm:pb-6 ${widthClass} sm:rounded-lg`}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-4 flex shrink-0 items-start justify-between gap-4">
          <h2 id="tjr-modal-title" className="font-serif text-lg text-wb-ink">
            {title}
          </h2>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close dialog"
            className="rounded-md p-1 text-wb-ink2 hover:text-wb-ink focus-visible:outline
              focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-wb-sage-deep"
          >
            ✕
          </button>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto pr-1">{children}</div>
      </div>
    </div>
  );
}
