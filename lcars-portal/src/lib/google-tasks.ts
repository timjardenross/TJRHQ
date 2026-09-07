// Google Tasks integration — server-only. Companion to google-calendar.ts:
// same OAuth connection (GOOGLE_OAUTH_SCOPES covers both), same trust
// boundary (kiosk/browser never touches Google directly).
//
// Purpose: let the Captain add tasks via the Google Tasks app (phone,
// watch, anywhere) and still have them picked up by the follow-through
// engine (intelligence/adhd/task_nudge_scheduler.py, follow_through_
// engine.py), which reads personal_tasks directly regardless of origin.
// This module only talks to Google; the actual two-way sync logic lives in
// /api/google-tasks/sync/route.ts.

import { getValidGoogleAccessToken, GoogleCalendarDisconnectedError } from '@/lib/google-calendar';

const TASKS_API_BASE = 'https://tasks.googleapis.com/tasks/v1';
const DEFAULT_TASK_LIST = '@default';

export interface GoogleTask {
  id: string;
  title: string;
  notes: string | null;
  due: string | null; // RFC3339 date (Google Tasks has no time component)
  status: 'needsAction' | 'completed';
  updated: string; // RFC3339 timestamp
}

async function googleTasksFetch(path: string, init?: RequestInit): Promise<Response> {
  const accessToken = await getValidGoogleAccessToken();
  const res = await fetch(`${TASKS_API_BASE}${path}`, {
    ...init,
    headers: {
      Authorization: `Bearer ${accessToken}`,
      'Content-Type': 'application/json',
      ...(init?.headers ?? {}),
    },
  });
  if (res.status === 401) {
    throw new GoogleCalendarDisconnectedError('Google Tasks access token was rejected. Reconnect required.');
  }
  return res;
}

/** Lists all incomplete + recently-completed tasks in the given list
 * (default: the account's default list). Google Tasks paginates via
 * nextPageToken — followed here since a task list realistically won't run
 * to thousands of items for a single-user app, but this loops rather than
 * assuming one page. */
export async function listGoogleTasks(taskListId: string = DEFAULT_TASK_LIST): Promise<GoogleTask[]> {
  const items: GoogleTask[] = [];
  let pageToken: string | undefined;

  do {
    const params = new URLSearchParams({
      showCompleted: 'true',
      showHidden: 'true',
      maxResults: '100',
    });
    if (pageToken) params.set('pageToken', pageToken);

    const res = await googleTasksFetch(`/lists/${encodeURIComponent(taskListId)}/tasks?${params.toString()}`);
    if (!res.ok) {
      const body = await res.text();
      throw new Error(`Google Tasks list fetch failed (${res.status}): ${body}`);
    }
    const data = (await res.json()) as { items?: GoogleTask[]; nextPageToken?: string };
    items.push(...(data.items ?? []));
    pageToken = data.nextPageToken;
  } while (pageToken);

  return items;
}

export interface UpsertGoogleTaskInput {
  title: string;
  notes?: string | null;
  due?: string | null; // date, e.g. "2026-09-12" — Google Tasks stores it as RFC3339 midnight UTC
  status?: 'needsAction' | 'completed';
}

/** Creates a new task in Google Tasks. Returns the created task's id. */
export async function createGoogleTask(
  input: UpsertGoogleTaskInput,
  taskListId: string = DEFAULT_TASK_LIST
): Promise<GoogleTask> {
  const res = await googleTasksFetch(`/lists/${encodeURIComponent(taskListId)}/tasks`, {
    method: 'POST',
    body: JSON.stringify(toGoogleTaskBody(input)),
  });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`Google Tasks create failed (${res.status}): ${body}`);
  }
  return res.json();
}

/** Patches an existing linked task (title/notes/due/status). */
export async function updateGoogleTask(
  taskId: string,
  input: UpsertGoogleTaskInput,
  taskListId: string = DEFAULT_TASK_LIST
): Promise<GoogleTask> {
  const res = await googleTasksFetch(`/lists/${encodeURIComponent(taskListId)}/tasks/${encodeURIComponent(taskId)}`, {
    method: 'PATCH',
    body: JSON.stringify(toGoogleTaskBody(input)),
  });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`Google Tasks update failed (${res.status}): ${body}`);
  }
  return res.json();
}

function toGoogleTaskBody(input: UpsertGoogleTaskInput): Record<string, unknown> {
  const body: Record<string, unknown> = { title: input.title };
  if (input.notes !== undefined) body.notes = input.notes;
  if (input.status !== undefined) body.status = input.status;
  if (input.due !== undefined) {
    // Google Tasks requires a full RFC3339 timestamp even though it only
    // stores the date part — midnight UTC on the given date.
    body.due = input.due ? `${input.due}T00:00:00.000Z` : null;
  }
  return body;
}
