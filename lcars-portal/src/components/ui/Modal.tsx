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

  const widthClass = variant === 'preview' ? 'max-w-3xl' : 'max-w-md';

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-wb-ink/40 p-4" onClick={onClose}>
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="tjr-modal-title"
        tabIndex={-1}
        className={`w-full ${widthClass} rounded-lg border border-wb-line bg-wb-surface p-6 shadow-lg
          focus-visible:outline focus-visible:outline-2 focus-visible:outline-wb-sage-deep`}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-4 flex items-start justify-between gap-4">
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
        {children}
      </div>
    </div>
  );
}
