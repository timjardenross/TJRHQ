'use client';

// Domains view — the five domain-grouped sections (Health / Operational
// Intelligence / Engineering / Learning / Opportunities), each a grid of
// ItemRows. Direct port of the LCARS page's DOMAIN_SECTIONS block.

import { Card } from './Shell';
import { ItemRow } from './ItemRow';
import type { CaptainBriefDocument } from './types';
import { DOMAIN_SECTIONS } from './types';

export function DomainsView({ doc }: { doc: CaptainBriefDocument }) {
  const anyContent = DOMAIN_SECTIONS.some(({ key }) => doc[key].length > 0);

  if (!anyContent) {
    return (
      <Card title="No Domain Signals">
        <p className="text-sm text-wb-ink2">
          No health, operational, engineering, learning, or opportunity items in the latest brief.
        </p>
      </Card>
    );
  }

  return (
    <>
      {DOMAIN_SECTIONS.map(({ key, label }) => {
        const items = doc[key];
        if (!items.length) return null;
        return (
          <Card key={key} title={label} className="mb-4">
            <ul className="grid grid-cols-1 gap-2 sm:grid-cols-2">
              {items.map((item, i) => (
                <ItemRow key={item.event_id ?? i} item={item} />
              ))}
            </ul>
          </Card>
        );
      })}
    </>
  );
}
