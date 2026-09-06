// Mission §25 — Settings must distinguish loading/saved/error, never fail
// a preference write silently. aria-live so a screen-reader user hears the
// outcome without having to go looking for it; text + shape (not colour
// alone) carries the meaning, per mission §26.
import type { SaveStatus } from './useSectionSettings';

export function SaveStatusLine({ status, onRetry }: { status: SaveStatus; onRetry?: () => void }) {
  if (status === 'loading') {
    return <p className="text-[12px] text-wb-ink2">Loading your settings…</p>;
  }
  if (status === 'saving') {
    return (
      <p role="status" aria-live="polite" className="text-[12px] text-wb-ink2">
        Saving…
      </p>
    );
  }
  if (status === 'saved') {
    return (
      <p role="status" aria-live="polite" className="text-[12px] font-medium text-wb-ok-on">
        Saved ✓
      </p>
    );
  }
  if (status === 'error') {
    return (
      <p role="alert" className="flex items-center gap-2 text-[12px] font-medium text-wb-crit-on">
        Could not save this setting.
        {onRetry && (
          <button type="button" onClick={onRetry} className="underline underline-offset-2 hover:no-underline">
            Try again
          </button>
        )}
      </p>
    );
  }
  return null;
}
