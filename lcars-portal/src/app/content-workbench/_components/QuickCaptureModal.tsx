'use client';

// Content Workbench's own "+ Capture Idea" trigger (MSN-0363, brief §6) —
// workbench-local, deliberately NOT the global floating QuickCapture in
// components/ui/ (that one writes to captured_items via lib/capture.ts,
// review-first, no scoring — a different pipeline entirely). This wraps
// the existing, unchanged CaptureBox (scores via contentScoring.ts,
// inserts into comms_content) in a compact button + Modal instead of
// CaptureBox's previous permanently-dominant page position.

import { useState } from 'react';
import { Modal } from '@/components/ui';
import { CaptureBox } from './CaptureBox';

export function QuickCaptureModal({ onCaptured, onDevelop }: { onCaptured: () => void; onDevelop?: (contentId: string) => void }) {
  const [open, setOpen] = useState(false);

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="inline-flex items-center gap-1.5 rounded-full bg-wb-sage-deep px-3.5 py-1.5 text-[12.5px] font-semibold text-white shadow-sm transition hover:opacity-90 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-wb-ink"
      >
        <span aria-hidden>+</span> Capture Idea
      </button>

      <Modal open={open} onClose={() => setOpen(false)} title="Capture Something">
        <CaptureBox
          onCaptured={onCaptured}
          onDevelop={(id) => { onDevelop?.(id); setOpen(false); }}
        />
      </Modal>
    </>
  );
}
