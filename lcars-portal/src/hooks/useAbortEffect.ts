import { useEffect } from 'react';

/**
 * useEffect for a fetch-driven effect: gives the effect body an
 * AbortController tied to its own lifecycle (aborted on cleanup — unmount
 * or a dependency change starting the next run) and an `alive()` guard for
 * state updates in `.then`/`.catch` chains that don't naturally short-
 * circuit on abort.
 *
 * 2026-09-15 adversarial review: ~45 of lcars-portal's `useEffect` data
 * fetches had no cleanup/AbortController — a fast route change or param
 * update could let a stale slower response overwrite state set by a
 * newer one (or by an unmounted component). This is the mechanical fix
 * for that pattern; pass `signal` to `fetch()` and check `alive()` before
 * any `setState` inside a `.then`/`.catch`.
 *
 * Usage:
 *   useAbortEffect((signal, alive) => {
 *     fetch(url, { signal })
 *       .then((r) => r.json())
 *       .then((d) => { if (alive()) setData(d); })
 *       .catch((e) => { if (alive() && e.name !== 'AbortError') setError(e); });
 *   }, [url]);
 */
export function useAbortEffect(
  effect: (signal: AbortSignal, alive: () => boolean) => void | (() => void),
  deps: React.DependencyList
): void {
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => {
    const controller = new AbortController();
    let cancelled = false;
    const alive = () => !cancelled && !controller.signal.aborted;
    const cleanup = effect(controller.signal, alive);
    return () => {
      cancelled = true;
      controller.abort();
      if (typeof cleanup === 'function') cleanup();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
}
