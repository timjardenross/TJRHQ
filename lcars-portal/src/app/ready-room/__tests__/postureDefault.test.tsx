// @vitest-environment jsdom
//
// Mission 2 (Capacity & Attention Engine, §19): Ready Room's initial
// Do/Unstick Me mode now defaults from today's Human Systems posture when
// the Captain hasn't already picked one -- RECOVER/RESET/PROTECT start on
// Unstick Me, ENGAGE/STEADY start on Do, UNKNOWN changes nothing. An
// explicit ?domain= URL param must always win over the posture default,
// and a toggle click must never be re-overridden by a later posture read.
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

describe('Ready Room initial mode — posture default (Mission 2 §19)', () => {
  it('defaults to Unstick Me when posture is RECOVER and no explicit domain param', async () => {
    mockSearchParam = null;
    mockHumanSystemsPosture('RECOVER');
    const { default: ReadyRoomWorkbench } = await import('../page');
    render(<ReadyRoomWorkbench />);
    await waitFor(() => expect(screen.getByTestId('decompose-view')).toBeInTheDocument());
  });

  it('defaults to Unstick Me when posture is PROTECT and no explicit domain param', async () => {
    mockSearchParam = null;
    mockHumanSystemsPosture('PROTECT');
    const { default: ReadyRoomWorkbench } = await import('../page');
    render(<ReadyRoomWorkbench />);
    await waitFor(() => expect(screen.getByTestId('decompose-view')).toBeInTheDocument());
  });

  it('defaults to Do when posture is STEADY and no explicit domain param', async () => {
    mockSearchParam = null;
    mockHumanSystemsPosture('STEADY');
    const { default: ReadyRoomWorkbench } = await import('../page');
    render(<ReadyRoomWorkbench />);
    await waitFor(() => expect(screen.getByTestId('today-stream')).toBeInTheDocument());
    expect(screen.queryByTestId('decompose-view')).not.toBeInTheDocument();
  });

  it('does not force a mode when posture is UNKNOWN -- keeps the pre-existing "do" default', async () => {
    mockSearchParam = null;
    mockHumanSystemsPosture('UNKNOWN');
    const { default: ReadyRoomWorkbench } = await import('../page');
    render(<ReadyRoomWorkbench />);
    await waitFor(() => expect(screen.getByTestId('today-stream')).toBeInTheDocument());
  });

  it('an explicit ?domain=unstick param wins even when posture is STEADY (Green)', async () => {
    mockSearchParam = 'unstick';
    mockHumanSystemsPosture('STEADY');
    const { default: ReadyRoomWorkbench } = await import('../page');
    render(<ReadyRoomWorkbench />);
    await waitFor(() => expect(screen.getByTestId('decompose-view')).toBeInTheDocument());
    // Posture resolves after mount; explicit param must still hold.
    await new Promise((r) => setTimeout(r, 10));
    expect(screen.getByTestId('decompose-view')).toBeInTheDocument();
  });

  it('an explicit ?domain=do param wins even when posture is RECOVER (Red-equivalent)', async () => {
    mockSearchParam = 'do';
    mockHumanSystemsPosture('RECOVER');
    const { default: ReadyRoomWorkbench } = await import('../page');
    render(<ReadyRoomWorkbench />);
    await waitFor(() => expect(screen.getByTestId('today-stream')).toBeInTheDocument());
    await new Promise((r) => setTimeout(r, 10));
    expect(screen.getByTestId('today-stream')).toBeInTheDocument();
  });
});
