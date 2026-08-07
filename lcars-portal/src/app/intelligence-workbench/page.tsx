'use client';

// Phase B — Intelligence Workbench · Screen 1 (Overview). Domain-toggled view.
// Supports both Operational Signals (Phase A) and Health Intelligence modes.
import Link from 'next/link';
import { useCallback, useEffect, useState } from 'react';
import { Card, RiskPill, WorkbenchShell, DomainToggle } from '@/components/ui';
import { commitHealthInsight, discardHealthInsight } from './_components/health-memory';
import { ClassifierValidationCard, AuditLogCard, PillarMappingsCard } from './_components/health-classifier-dashboard';
import { useRealtimeRefresh } from '@/lib/realtime/useRealtimeRefresh';

type Domain = 'confidence-matrix' | 'intelligence-summary' | 'source-network' | 'threat-assessment';

type Brief = {
  brief_id: string;
  overall_risk: string | null;
  approval_status: string | null;
  executive_snapshot: string | null;
  signal_ids: string[] | null;
};

type Signal = {
  event_id: string;
  raw_title: string;
  sector: string | null;
  geography: string | null;
  risk_rating: string | null;
  rank_score: number | null;
  source_tier: number | null;
  canonical_url: string | null;
};

type SourceArticle = {
  title: string;
  url: string;
  summary?: string;
  published_date?: string;
  source_type?: string;
};

type HealthInsight = {
  insight_id: string;
  created_at: string;
  overall_status: string | null;
  wellness_narrative: string | null;
  key_findings: string | null;
  source_articles?: SourceArticle[] | null;
  committed_to_memory?: boolean;
  committed_at?: string | null;
};

type HealthEvent = {
  event_id: string;
  logged_at: string;
  event_type: string;
  value: number | string | null;
  notes: string | null;
  source: string | null;
};

type Payload = {
  domain: Domain;
  [key: string]: any;
};

// Local inline toggle removed (WORKBENCH-REVIEW.md H9/H12, 2026-07-18) - it
// had no role/aria-selected/keyboard handling at all, the least accessible
// of every *-workbench domain toggle. Replaced with the shared, properly
// keyboard-navigable DomainToggle from @/components/ui.
const DOMAIN_OPTIONS: { key: Domain