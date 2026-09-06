'use client';

// Mission §11-14 — the human-editable configuration behind the Technical
// and Health OSINT relevance gates, WITHOUT becoming an intelligence-
// analysis screen or a second copy of the taxonomy.
//
// Category/tag keys+labels come from /api/settings/intelligence/taxonomy,
// a read-only mirror of config/osint_intelligence_missions.json (the one
// source of truth — see that route's own comment on why this file stays
// git-tracked/hand-edited rather than becoming DB-editable). What gets
// checked here is a separate on/off OVERLAY, persisted in user_settings
// and read by intelligence/settings_store.py — the flow mission §14
// diagrams as "Settings chooses → ingestion consumes → workbenches see
// only what's relevant", never Settings performing relevance assessment
// itself.
//
// An empty enabled list means "every current AND future category/tag
// enabled" (the safe default — see lib/settings.ts). To keep that
// forward-compatible property intact, checking every currently-known
// item collapses the stored list back to [] rather than an explicit
// "all of today's keys" list — see saveTechnical/saveHealth below.
import { useEffect, useState } from 'react';
import { Checkbox } from '@/components/ui/Input';
import { SectionHeading } from './SectionHeading';
import { SaveStatusLine } from './SaveStatusLine';
import { useSectionSettings } from './useSectionSettings';

interface TechnicalCategory {
  key: string;
  label: string;
}
interface HealthTierTags {
  key: string;
  label: string;
  tags: { key: string; label: string }[];
}
interface Taxonomy {
  technical: TechnicalCategory[];
  health: HealthTierTags[];
}

function toggledEnabledList(allKeys: string[], currentEnabled: string[], key: string, checked: boolean): string[] {
  const current = new Set(currentEnabled.length === 0 ? allKeys : currentEnabled);
  if (checked) current.add(key);
  else current.delete(key);
  return current.size === allKeys.length ? [] : Array.from(current);
}

export function IntelligenceSection() {
  const { value, status, save } = useSectionSettings('intelligence');
  const [taxonomy, setTaxonomy] = useState<Taxonomy | null>(null);
  const [taxonomyError, setTaxonomyError] = useState(false);

  useEffect(() => {
    let cancelled = false;
    fetch('/api/settings/intelligence/taxonomy')
      .then((res) => {
        if (!res.ok) throw new Error('load failed');
        return res.json();
      })
      .then((body: Taxonomy) => {
        if (!cancelled) setTaxonomy(body);
      })
      .catch(() => {
        if (!cancelled) setTaxonomyError(true);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const allTechnicalKeys = taxonomy?.technical.map((c) => c.key) ?? [];
  const allHealthKeys = taxonomy?.health.flatMap((t) => t.tags.map((tag) => tag.key)) ?? [];

  function isTechnicalEnabled(key: string): boolean {
    return value.technical.enabledCategories.length === 0 || value.technical.enabledCategories.includes(key);
  }
  function isHealthEnabled(key: string): boolean {
    return value.health.enabledTags.length === 0 || value.health.enabledTags.includes(key);
  }

  function toggleTechnical(key: string, checked: boolean) {
    save({
      ...value,
      technical: {
        ...value.technical,
        enabledCategories: toggledEnabledList(allTechnicalKeys, value.technical.enabledCategories, key, checked),
      },
    });
  }
  function toggleHealth(key: string, checked: boolean) {
    save({
      ...value,
      health: { enabledTags: toggledEnabledList(allHealthKeys, value.health.enabledTags, key, checked) },
    });
  }

  const loading = status === 'loading' || !taxonomy;

  return (
    <div>
      <SectionHeading
        title="Intelligence"
        description="What HQ should care about. These are monitoring priorities, not an intelligence-analysis screen."
      />

      {taxonomyError && (
        <p role="alert" className="mb-4 text-[12px] font-medium text-wb-crit-on">
          Could not load the category list. Showing a smaller built-in set instead.
        </p>
      )}

      <section className="mb-8">
        <h2 className="mb-1 text-[13px] font-semibold uppercase tracking-[0.1em] text-wb-ink2">Technical Intelligence</h2>
        <p className="mb-3 text-[12px] text-wb-ink2">HQ is monitoring:</p>
        <div className="grid grid-cols-1 gap-x-6 gap-y-1 rounded-lg border border-wb-line bg-wb-surface p-4 sm:grid-cols-2">
          {(taxonomy?.technical ?? []).map((category) => (
            <Checkbox
              key={category.key}
              label={category.label}
              checked={isTechnicalEnabled(category.key)}
              disabled={loading}
              onChange={(e) => toggleTechnical(category.key, e.target.checked)}
            />
          ))}
        </div>

        <p className="mb-2 mt-4 text-[12px] text-wb-ink2">Geographic focus:</p>
        <fieldset className="flex flex-col gap-2 rounded-lg border border-wb-line bg-wb-surface p-4">
          <legend className="sr-only">Geographic focus</legend>
          {(
            [
              ['au', 'Australia first'],
              ['apac', 'Australia + APAC'],
              ['global', 'Global'],
            ] as const
          ).map(([key, label]) => (
            <label key={key} className="flex cursor-pointer items-center gap-2 text-[13px] text-wb-ink">
              <input
                type="radio"
                name="geographic-focus"
                className="h-4 w-4 border-wb-line text-wb-sage-deep focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-wb-sage-deep"
                checked={value.technical.geographicFocus === key}
                disabled={loading}
                onChange={() => save({ ...value, technical: { ...value.technical, geographicFocus: key } })}
              />
              {label}
            </label>
          ))}
        </fieldset>
        <p className="mt-2 text-[11px] text-wb-ink2">
          Systemic global events are still considered where they could materially affect a monitored area, regardless of this
          setting.
        </p>
      </section>

      <section>
        <h2 className="mb-1 text-[13px] font-semibold uppercase tracking-[0.1em] text-wb-ink2">Health Intelligence</h2>
        <p className="mb-3 text-[12px] text-wb-ink2">
          Monitoring-interest preferences, not diagnoses or medical conclusions.
        </p>
        <div className="flex flex-col gap-4">
          {(taxonomy?.health ?? []).map((tier) => (
            <div key={tier.key} className="rounded-lg border border-wb-line bg-wb-surface p-4">
              <h3 className="mb-2 text-[12px] font-semibold uppercase tracking-[0.08em] text-wb-ink2">{tier.label}</h3>
              <div className="grid grid-cols-1 gap-x-6 gap-y-1 sm:grid-cols-2">
                {tier.tags.map((tag) => (
                  <Checkbox
                    key={tag.key}
                    label={tag.label}
                    checked={isHealthEnabled(tag.key)}
                    disabled={loading}
                    onChange={(e) => toggleHealth(tag.key, e.target.checked)}
                  />
                ))}
              </div>
            </div>
          ))}
        </div>
      </section>

      <div className="mt-4">
        <SaveStatusLine status={status} onRetry={() => save(value)} />
      </div>
    </div>
  );
}
