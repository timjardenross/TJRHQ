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

  useEffect(() => {
    if (!open) return;
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === 'Escape') onClose();
    }
    document.addEventListener('keydown', onKeyDown);
    panelRef.current?.focus();
    return () => document.removeEventListener('keydown', onKeyDown);
  }, [open, onClose]);

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
  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-wb-ink/40 sm:items-center sm:p-4" onClick={onClose}>
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="tjr-modal-title"
        tabIndex={-1}
        className={`flex max-h-[90dvh] w-full flex-col rounded-t-2xl border border-wb-line bg-wb-surface p-6 shadow-lg
          focus-visible:outline focus-visible:outline-2 focus-visible:outline-wb-sage-deep
          sm:max-h-[85vh] ${widthClass} sm:rounded-lg`}
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
