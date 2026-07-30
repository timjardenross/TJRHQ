// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook } from '@testing-library/react';

// Mirrors decide.test.ts's mocking boundary: assert exactly which table/
// event/filter the hook subscribes to, and that it never fetches or shapes
// data itself - onChange is the only thing it's allowed to call.
const onMock = vi.fn();
const subscribeMock = vi.fn((cb?: (status: string) => void) => {
  cb?.('SUBSCRIBED');
  return { unsubscribe: vi.fn() };
});
const channelMock = vi.fn(() => ({
  on: onMock.mockReturnThis(),
  subscribe: subscribeMock,
}));
const removeChannelMock = vi.fn();

vi.mock('@/lib/supabase-browser', () => ({
  createSupabaseBrowserClient: () => ({
    channel: channelMock,
    removeChannel: removeChannelMock,
  }),
}));

import { useRealtimeRefresh } from '@/lib/realtime/useRealtimeRefresh';

beforeEach(() => {
  vi.clearAllMocks();
  onMock.mockReturnThis();
  subscribeMock.mockImplementation((cb?: (status: string) => void) => {
    cb?.('SUBSCRIBED');
    return { unsubscribe: vi.fn() };
  });
});

describe('useRealtimeRefresh', () => {
  it('subscribes to postgres_changes for the given table and default INSERT event', () => {
    renderHook(() => useRealtimeRefresh({ table: 'intelligence_events', onChange: vi.fn() }));
    expect(channelMock).toHaveBeenCalledWith(expect.stringContaining('intelligence_events'));
    expect(onMock).toHaveBeenCalledWith(
      'postgres_changes',
      expect.objectContaining({ event: 'INSERT', schema: 'public', table: 'intelligence_events' }),
      expect.any(Function),
    );
  });

  it('calls onChange when the subscribed callback fires', () => {
    const onChange = vi.fn();
    renderHook(() => useRealtimeRefresh({ table: 'intelligence_events', onChange }));
    const handler = onMock.mock.calls[0][2];
    handler();
    expect(onChange).toHaveBeenCalledTimes(1);
  });

  it('reports SUBSCRIBED via onStatusChange once connected', () => {
    const onStatusChange = vi.fn();
    renderHook(() => useRealtimeRefresh({ table: 'intelligence_events', onChange: vi.fn(), onStatusChange }));
    expect(onStatusChange).toHaveBeenCalledWith('SUBSCRIBED');
  });

  it('does not subscribe when enabled is false', () => {
    renderHook(() => useRealtimeRefresh({ table: 'intelligence_events', onChange: vi.fn(), enabled: false }));
    expect(channelMock).not.toHaveBeenCalled();
  });

  it('passes an optional filter through to postgres_changes', () => {
    renderHook(() =>
      useRealtimeRefresh({ table: 'intelligence_events', onChange: vi.fn(), filter: 'domain=eq.operational' }),
    );
    expect(onMock).toHaveBeenCalledWith(
      'postgres_changes',
      expect.objectContaining({ filter: 'domain=eq.operational' }),
      expect.any(Function),
    );
  });

  it('removes the channel on unmount', () => {
    const { unmount } = renderHook(() => useRealtimeRefresh({ table: 'intelligence_events', onChange: vi.fn() }));
    unmount();
    expect(removeChannelMock).toHaveBeenCalled();
  });
});
