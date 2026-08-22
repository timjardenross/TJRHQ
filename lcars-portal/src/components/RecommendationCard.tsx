import { DataSourceIndicator } from './DataSourceIndicator';

/**
 * Command Centre's recommended-action shape (`command-centre.ts`). `confidence`
 * is a backend-authored textual descriptor (e.g. "High — today's brief"), not
 * a 0-100 score — do not route it through `ConfidenceIndicator`, which expects
 * a numeric score. The two concepts look similar but have different shapes;
 * forcing one into the other would require a backend contract change, out of
 * scope for a component-consolidation pass.
 */
export interface RecommendedAction {
  action: string;
  why?: string;
  sourceOfficer: string;
  confidence: string;
  /**
   * MSN-0344: supporting evidence strings for this recommendation — optional
   * and additive. Rendered as a collapsed `<details>` disclosure so existing
   * callers that don't pass it see zero change. Backend contract already
   * carries this (`Recommendation.evidence: string[]`, captain_brief_contract.py)
   * — it was typed on the Captain's Brief page but never rendered anywhere
   * until now (found during MSN-0344's explainability review).
   */
  evidence?: string[];
}

export interface RecommendationCardProps {
  recommendation: RecommendedAction | null;
  isLoading?: boolean;
  isLive?: boolean;
  title?: string;
  emptyMessage?: string;
  loadingMessage?: string;
  /** Compact drops the `why` line and the live indicator — for dense mobile cards. Evidence disclosure still shows if present. */
  compact?: boolean;
}

export function RecommendationCard({
  recommendation,
  isLoading = false,
  isLive,
  title = 'Recommended Action',
  emptyMessage = 'No recommendation available — run the daily brief.',
  loadingMessage = 'Reading the daily operating picture…',
  compact = false,
}: RecommendationCardProps) {
  return (
    <div className="rounded-lg border border-wb-sage-deep/40 bg-wb-sage-deep/5 p-3">
      <div className="mb-1.5 flex items-center justify-between">
        <p className="text-[10px] font-bold uppercase tracking-[0.25em] text-wb-ink2">{title}</p>
        {!compact && isLive !== undefined && <DataSourceIndicator live={isLive} variant="inline" />}
      </div>

      {recommendation ? (
        <div className="flex flex-col gap-1.5">
          <p className={`text-sm font-semibold leading-snug ${compact ? 'text-wb-sage-deep' : 'text-wb-ink'}`}>
            {recommendation.action}
          </p>
          {!compact && recommendation.why && <p className="text-[11px] text-wb-ink/70">{recommendation.why}</p>}
          {compact ? (
            <p className="text-[11px] text-wb-ink2">
              {recommendation.sourceOfficer} · {recommendation.confidence}
            </p>
          ) : (
            <div className="mt-1 flex flex-wrap items-center gap-x-4 gap-y-1 text-[10px] uppercase tracking-wide">
              <span className="text-wb-sage-deep">{recommendation.sourceOfficer}</span>
              <span className="text-wb-ink2">Confidence · {recommendation.confidence}</span>
            </div>
          )}
          {recommendation.evidence && recommendation.evidence.length > 0 && (
            <details className="mt-1 text-[11px]">
              <summary className="cursor-pointer text-wb-ink2 hover:text-wb-ink">
                Evidence ({recommendation.evidence.length})
              </summary>
              <ul className="mt-1 flex flex-col gap-0.5 pl-3">
                {recommendation.evidence.map((e, i) => (
                  <li key={i} className="list-disc text-wb-ink/70">{e}</li>
                ))}
              </ul>
            </details>
          )}
        </div>
      ) : (
        <p className="text-[11px] text-wb-ink2">{isLoading ? loadingMessage : emptyMessage}</p>
      )}
    </div>
  );
}
