import { Fragment } from 'react';

export interface ProgressBarProps {
  /** 0–max */
  value: number;
  max?: number;
  label?: string;
}

/** TJR Design System — generalized from the escalation page's 10-dimension risk bars. */
export function ProgressBar({ value, max = 100, label }: ProgressBarProps) {
  const pct = Math.max(0, Math.min(100, (value / max) * 100));
  return (
    <div className="flex items-center gap-2 text-[12.5px]">
      {label && <span className="w-[130px] text-wb-ink">{label}</span>}
      <span
        role="progressbar"
        aria-valuenow={value}
        aria-valuemin={0}
        aria-valuemax={max}
        aria-label={label}
        className="h-1.5 flex-1 overflow-hidden rounded bg-wb-line"
      >
        <span className="block h-full bg-wb-sage" style={{ width: `${pct}%` }} />
      </span>
      <span className="w-8 text-right text-wb-ink2">
        {value}/{max}
      </span>
    </div>
  );
}

export interface ProgressStep {
  key: string;
  label: string;
  complete: boolean;
}

export interface ProgressStepsProps {
  steps: ProgressStep[];
}

/** TJR Design System — generalized from the brief page's approval-gate stepper. */
export function ProgressSteps({ steps }: ProgressStepsProps) {
  return (
    <ol className="flex flex-wrap items-center gap-3" aria-label="Progress">
      {steps.map((s, i) => (
        <Fragment key={s.key}>
          <li className="flex items-center gap-2 text-[12px]">
            <span
              aria-hidden
              className={`grid h-5 w-5 place-items-center rounded text-[11px] text-white ${
                s.complete ? 'bg-wb-ok' : 'bg-wb-line'
              }`}
            >
              {s.complete ? '✓' : i + 1}
            </span>
            <span className={s.complete ? 'text-wb-ink' : 'text-wb-ink2'}>
              {s.label}
              <span className="sr-only">{s.complete ? ' (complete)' : ' (pending)'}</span>
            </span>
          </li>
        </Fragment>
      ))}
    </ol>
  );
}
