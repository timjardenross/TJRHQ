-- ============================================================
-- M-20260612-HEALTH-CAPACITY-CALIBRATION
-- Schema migrations — apply via Supabase SQL Editor
-- ============================================================

-- ── WP1: Captain self-rated capacity field ───────────────────

ALTER TABLE public.captains_log_entries
  ADD COLUMN IF NOT EXISTS captain_capacity_rating TEXT
    CHECK (captain_capacity_rating IN ('Green', 'Amber', 'Red'));

COMMENT ON COLUMN public.captains_log_entries.captain_capacity_rating
  IS 'Captain self-rated operational capacity: Green | Amber | Red. Independent of system Capacity Score.';


-- ── WP2: Daily calibration rows ──────────────────────────────

CREATE TABLE IF NOT EXISTS public.capacity_calibration (
  id                    BIGSERIAL PRIMARY KEY,
  log_date              DATE        NOT NULL UNIQUE,
  capacity_score        INTEGER,
  capacity_status       TEXT CHECK (capacity_status IN ('Green','Amber','Red','Unknown')),
  captain_rating        TEXT CHECK (captain_rating   IN ('Green','Amber','Red')),
  agreement             BOOLEAN,
  mismatch_type         TEXT,        -- false_green | false_amber | false_red | null
  weekly_agreement_pct  NUMERIC(5,2),
  rolling_30d_pct       NUMERIC(5,2),
  calculated_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at            TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_capacity_calibration_log_date
  ON public.capacity_calibration (log_date DESC);


-- ── WP2: Calibration summary (one row per run) ───────────────

CREATE TABLE IF NOT EXISTS public.capacity_calibration_summary (
  id                     BIGSERIAL PRIMARY KEY,
  summary_date           DATE        NOT NULL UNIQUE,
  window_days            INTEGER     NOT NULL DEFAULT 30,
  total_days_compared    INTEGER     NOT NULL DEFAULT 0,
  agreement_count        INTEGER     NOT NULL DEFAULT 0,
  agreement_rate         NUMERIC(5,2),
  false_green_count      INTEGER     NOT NULL DEFAULT 0,
  false_amber_count      INTEGER     NOT NULL DEFAULT 0,
  false_red_count        INTEGER     NOT NULL DEFAULT 0,
  calibration_confidence TEXT CHECK (calibration_confidence IN ('high','medium','low','insufficient')),
  consecutive_low_days   INTEGER     NOT NULL DEFAULT 0,
  weighting_review_flag  BOOLEAN     NOT NULL DEFAULT FALSE,
  calculated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_cap_cal_summary_date
  ON public.capacity_calibration_summary (summary_date DESC);


-- ── Auto-update trigger ──────────────────────────────────────

CREATE OR REPLACE FUNCTION update_capacity_calibration_updated_at()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN NEW.updated_at = NOW(); RETURN NEW; END;
$$;

DROP TRIGGER IF EXISTS trg_cap_cal_updated_at ON public.capacity_calibration;
CREATE TRIGGER trg_cap_cal_updated_at
  BEFORE UPDATE ON public.capacity_calibration
  FOR EACH ROW EXECUTE FUNCTION update_capacity_calibration_updated_at();
