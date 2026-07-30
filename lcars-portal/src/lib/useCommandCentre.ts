'use client';

/**
 * useCommandCentre — live Captain's Chair command-centre data (CCP-001).
 *
 * Mirrors useROSData: fetches on mount from the reuse-first command-centre
 * fetchers and degrades to neutral placeholders so the strip always renders.
 */

import { useEffect, useState } from 'react';
import {
  fetchRecommendedAction,
  fetchShipStatus,
  fetchWhatChanged,
  fetchOfficerActivity,
  type RecommendedAction,
  type ShipDomain,
  type ChangeItem,
  type ActivityEvent,
} from './command-centre';

export interface CommandCentreData {
  recommendedAction: RecommendedAction | null;
  shipStatus: ShipDomain[];
  whatChanged: ChangeItem[];
  activity: ActivityEvent[];
  isLive: boolean;
  isLoading: boolean;
}

const EMPTY: CommandCentreData = {
  recommendedAction: null,
  shipStatus: [],
  whatChanged: [],
  activity: [],
  isLive: false,
  isLoading: true,
};

export function useCommandCentre(): CommandCentreData {
  const [state, setState] = useState<CommandCentreData>(EMPTY);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      const [action, status, changed, activity] = await Promise.all([
        fetchRecommendedAction(),
        fetchShipStatus(),
        fetchWhatChanged(),
        fetchOfficerActivity(),
      ]);
      if (cancelled) return;
      setState({
        recommendedAction: action,
        shipStatus: status ?? [],
        whatChanged: changed ?? [],
        activity: activity ?? [],
        isLive: action !== null || (status?.length ?? 0) > 0,
        isLoading: false,
      });
    }
    load();
    return () => { cancelled = true; };
  }, []);

  return state;
}
