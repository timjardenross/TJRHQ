'use client';

/**
 * useROSData — React hook for live ROS-001 data.
 *
 * Fetches all Recovery Operating System data from Supabase on mount.
 * Falls back to mock data for any field where the live fetch returns null
 * (no connection, no env vars, or no health check-in for today).
 */

import { useEffect, useState } from 'react';
import {
  bodyContext      as mockBodyContext,
  emotionalLoadFlag as mockEmotionalLoadFlag,
  lifeParticipationScore as mockLPS,
  postureHistory   as mockPostureHistory,
  recoveryGuidance as mockGuidance,
  recoveryIndexes  as mockIndexes,
  recoveryPosture  as mockPosture,
  weeklyPatternSummary as mockWeeklySummary
} from './mockData';
import {
  fetchBodyContext,
  fetchEmotionalLoadFlag,
  fetchLifeParticipation,
  fetchPostureHistory,
  fetchRecoveryIndexes,
  fetchRecoveryPosture,
  fetchWeeklyPatternSummary
} from './ros-data';
import type {
  BodyContext,
  EmotionalLoadFlag,
  LifeParticipationScore,
  PostureHistory,
  RecoveryIndex,
  RecoveryPosture,
  WeeklyPatternSummary
} from './types';

export interface ROSData {
  posture:           RecoveryPosture;
  bodyContext:       BodyContext;
  postureHistory:    PostureHistory;
  weeklySummary:     WeeklyPatternSummary;
  emotionalLoadFlag: EmotionalLoadFlag;
  lifeParticipation: LifeParticipationScore;
  recoveryIndexes:   RecoveryIndex[];
  guidance:          string[];
  isLive:            boolean; // true when at least posture came from Supabase
  isLoading:         boolean;
}

export function useROSData(): ROSData {
  const [state, setState] = useState<ROSData>({
    posture:           mockPosture,
    bodyContext:       mockBodyContext,
    postureHistory:    mockPostureHistory,
    weeklySummary:     mockWeeklySummary,
    emotionalLoadFlag: mockEmotionalLoadFlag,
    lifeParticipation: mockLPS,
    recoveryIndexes:   mockIndexes,
    guidance:          mockGuidance,
    isLive:            false,
    isLoading:         true
  });

  useEffect(() => {
    let cancelled = false;

    async function load() {
      const [
        livePosture,
        liveBody,
        liveHistory,
        liveWeekly,
        liveFlag,
        liveLPS,
        liveIndexes
      ] = await Promise.all([
        fetchRecoveryPosture(),
        fetchBodyContext(),
        fetchPostureHistory(7),
        fetchWeeklyPatternSummary(),
        fetchEmotionalLoadFlag(),
        fetchLifeParticipation(),
        fetchRecoveryIndexes()
      ]);

      if (cancelled) return;

      setState({
        posture:           livePosture  ?? mockPosture,
        bodyContext:       liveBody     ?? mockBodyContext,
        postureHistory:    liveHistory  ?? mockPostureHistory,
        weeklySummary:     liveWeekly   ?? mockWeeklySummary,
        emotionalLoadFlag: liveFlag     ?? mockEmotionalLoadFlag,
        lifeParticipation: liveLPS      ?? mockLPS,
        recoveryIndexes:   liveIndexes  ?? mockIndexes,
        guidance:          mockGuidance, // Phase 2: replace with health_insights fetch
        isLive:            livePosture !== null,
        isLoading:         false
      });
    }

    load();
    return () => { cancelled = true; };
  }, []);

  return state;
}
