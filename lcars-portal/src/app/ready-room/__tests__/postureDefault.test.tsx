// @vitest-environment jsdom
//
// Ready Room's initial Do/Unstick Me mode is always "Do" unless the Captain picks
// otherwise (owner decision 2026-11-02): capacity posture no longer changes the default.
// An explicit ?domain= URL param still wins.
import { afterEach, describe, expect, it, vi } from 'vitest';
import { render, screen, cleanup, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';

let mockSearchParam: string | null = null;
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: () => {}, replace: () => {} }),
  usePathname: () => '/ready-room',
  useSearchParams: () => ({ get: (key: string) => (key === 'domain' ? mockSearchParam : null), entries: () => [][Symbol.iterator]() }),
}));

vi.mock('../_components/TodayStream', () => ({
  TodayStream: () => <div data-testid="today-stream" /> as unknown as null,
}));
vi.mock('../_components/DecomposeView', () => ({
  DecomposeView: () => <div data-testid="decompose-view" /> as unknown as null,
}));

function mockHumanSystemsPosture(posture: string | null) {
  vi.stubGlobal('fetch', vi.fn((input: RequestInfo | URL) => {
    const url = typeof input === 'string' ? input : input.toString();
    if (url.startsWith('/api/human-systems/context')) {
      return Promise.resolve({
        ok: true,
        json: async () => (posture === null ? {} : { posture, posture_message: '', available_capacity: 'unknown', has_checkin_today: true }),
      } as Response);
    }
    if (url.startsWith('/api/ready-room/sync-status')) {
      return Promise.resolve({ ok: true, json: async () => ({}) } as Response);
    }
    return Promise.resolve({ ok: true, json: async () => ({}) } as Response);
  }));
}

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  mockSearchParam = null;
});

describe('Ready Room initial mode — posture never changes the default', () => {
  it.each(['RECOVER', 'PROTECT', 'RESET', 'STEADY', 'ENGAGE', 'UNKNOWN'])(
    'starts on Do when posture is %s and no explicit domain param',
    async (posture) => {
      mockSearchParam = null;
      mockHumanSystemsPosture(posture);
      const { default: ReadyRoomWorkbench } = await import('../page');
      render(<ReadyRoomWorkbench />);
      await waitFor(() => expect(screen.getByTestId('today-stream')).toBeInTheDocument());
      await new Promise((r) => setTimeout(r, 10));
      expect(screen.queryByTestId('decompose-view')).not.toBeInTheDocument();
    },
  );

  it('an explicit ?domain=unstick param is respected', async () => {
    mockSearchParam = 'unstick';
    mockHumanSystemsPosture('STEADY');
    const { default: ReadyRoomWorkbench } = await import('../page');
    render(<ReadyRoomWorkbench />);
    await waitFor(() => expect(screen.getByTestId('decompose-view')).toBeInTheDocument());
  });
});
