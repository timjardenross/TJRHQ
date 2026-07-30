'use client';

import { useEffect, useState, useCallback } from 'react';
import { StatTile } from '@/components/StatTile';
import type { KnowledgeLibraryStats } from '@/lib/types';
import { fetchJson } from '@/lib/knowledgeLibraryClient';

interface LibraryKpisProps {
  onStatsUpdate?: (stats: KnowledgeLibraryStats | null) => void;
}

export function LibraryKpis({ onStatsUpdate }: LibraryKpisProps) {
  const [stats, setStats] = useState<KnowledgeLibraryStats | null>(null);

  const loadStats = useCallback(async () => {
    try {
      const data = await fetchJson('/api/knowledge-library/stats');
      setStats(data);
      if (onStatsUpdate) onStatsUpdate(data);
    } catch {
      /* stats are a nice-to-have; loadDocuments surfaces the shared error banner */
    }
  }, [onStatsUpdate]);

  useEffect(() => {
    loadStats();
  }, [loadStats]);

  return (
    <div className="flex flex-col gap-4">
      <div>
        <p className="mb-2 text-[10px] uppercase tracking-[0.2em] text-wb-ink2">
          Pipeline Health — system status, nothing here is yours to act on
        </p>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <StatTile label="Total Documents" value={stats?.total_documents ?? '—'} accent="science" />
          <StatTile label="In Progress" value={stats?.in_progress ?? '—'} accent="engineering" />
          <StatTile label="OCR Required" value={stats?.ocr_required ?? '—'} accent="engineering" />
          <StatTile label="Failed" value={stats?.failed_documents ?? '—'} accent="operations" />
        </div>
      </div>
      <div>
        <p className="mb-2 text-[10px] uppercase tracking-[0.2em] text-wb-ink2">
          Your Review Queue — needs a decision from you
        </p>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-5">
          <StatTile label="Needs Your Review" value={stats?.needs_your_review ?? '—'} accent="command" />
          <StatTile label="Needs Follow-Up" value={stats?.needs_followup ?? '—'} accent="command" />
          <StatTile label="Approved to Memory" value={stats?.memory_approved ?? '—'} accent="medical" />
          <StatTile label="Rejected" value={stats?.rejected ?? '—'} accent="operations" />
          <StatTile label="Reviewed Today" value={stats?.decided_today ?? '—'} accent="science" />
        </div>
      </div>
    </div>
  );
}
