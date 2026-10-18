// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

const rows = [
  { id: 'a', name: 'Goblet squat', equipment: 'Kettlebell', movement_pattern: 'squat', difficulty: 'easy', status: 'active', primary_muscles_json: ['quads'], default_sets: 3, default_reps: '8', default_duration_minutes: null, pain_cautions_json: { knee: 6 }, regression: 'Box squat', progression: 'Front squat', preferred_video_url: null, video_search_query: 'goblet squat' },
  { id: 'b', name: 'Deadlift', equipment: 'Barbell', movement_pattern: 'hinge', difficulty: 'hard', status: 'avoid', primary_muscles_json: ['glutes'], default_sets: 3, default_reps: '5', default_duration_minutes: null, pain_cautions_json: {}, regression: null, progression: null, preferred_video_url: 'https://example.com/dl', video_search_query: 'deadlift' },
];
vi.mock('@/lib/supabase-browser', () => ({
  createSupabaseBrowserClient: () => ({
    from: () => ({ select: () => ({ order: () => ({ order: () => Promise.resolve({ data: rows }) }) }) }),
  }),
}));
import { ExerciseLibraryView } from '../ExerciseLibraryView';

describe('ExerciseLibraryView (moved from Physical Readiness into Knowledge)', () => {
  afterEach(cleanup);

  it('groups the catalogue by equipment, shows status, and reports the count', async () => {
    const onCount = vi.fn();
    render(<ExerciseLibraryView onCount={onCount} />);
    await screen.findByText('Goblet squat');
    expect(screen.getByText('Kettlebell')).toBeTruthy();
    expect(screen.getByText('Barbell')).toBeTruthy();
    expect(screen.getByText('avoid')).toBeTruthy();
    expect(onCount).toHaveBeenCalledWith(2);
  });

  it('expands an exercise to its detail and video link', async () => {
    render(<ExerciseLibraryView />);
    fireEvent.click(await screen.findByText('Deadlift'));
    await waitFor(() => expect(screen.getByText(/Find Guide Video/)).toBeTruthy());
    expect(screen.getByText(/Find Guide Video/).closest('a')?.getAttribute('href')).toBe('https://example.com/dl');
  });
});
