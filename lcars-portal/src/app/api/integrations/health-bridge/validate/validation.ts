export const MAX_BODY_BYTES = 32 * 1024;
export const SUPPORTED_SCHEMA_VERSION = '1.0';

const DATE_PATTERN = /^\d{4}-\d{2}-\d{2}$/;
const TIMEZONE_PATTERN = /^[A-Za-z_]+(?:\/[A-Za-z0-9_+\-]+)+$/;
const QUALITY_VALUES = new Set(['unavailable', 'not_collected', 'partial', 'valid', 'corrected']);

export type ValidationIssue = {
  path: string;
  message: string;
};

export type HealthBridgeSummary = {
  schema_version: string;
  date: string;
  timezone: string;
  activity?: {
    steps?: number;
    walking_distance_km?: number;
  };
  recovery?: {
    resting_heart_rate_bpm?: number;
    hrv_sdnn_ms?: number;
  };
  sleep?: {
    duration_minutes?: number;
    source?: 'healthkit' | 'manual';
  };
  workouts?: Array<{
    duration_minutes: number;
    type?: string;
  }>;
  quality?: Partial<Record<'activity' | 'recovery' | 'sleep' | 'workouts', string>>;
};

const TOP_LEVEL_FIELDS = new Set([
  'schema_version',
  'date',
  'timezone',
  'activity',
  'recovery',
  'sleep',
  'workouts',
  'quality',
]);
const ACTIVITY_FIELDS = new Set(['steps', 'walking_distance_km']);
const RECOVERY_FIELDS = new Set(['resting_heart_rate_bpm', 'hrv_sdnn_ms']);
const SLEEP_FIELDS = new Set(['duration_minutes', 'source']);
const WORKOUT_FIELDS = new Set(['duration_minutes', 'type']);
const QUALITY_FIELDS = new Set(['activity', 'recovery', 'sleep', 'workouts']);

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function unknownFields(value: Record<string, unknown>, allowed: Set<string>, path: string): ValidationIssue[] {
  return Object.keys(value)
    .filter((key) => !allowed.has(key))
    .map((key) => ({ path: path ? `${path}.${key}` : key, message: 'unknown field' }));
}

function numberInRange(
  value: unknown,
  path: string,
  minimum: number,
  maximum: number,
  integer = false,
): ValidationIssue[] {
  if (typeof value !== 'number' || !Number.isFinite(value)) {
    return [{ path, message: 'must be a finite number' }];
  }
  if (integer && !Number.isInteger(value)) {
    return [{ path, message: 'must be an integer' }];
  }
  if (value < minimum || value > maximum) {
    return [{ path, message: `must be between ${minimum} and ${maximum}` }];
  }
  return [];
}

function validateDate(value: unknown): ValidationIssue[] {
  if (typeof value !== 'string' || !DATE_PATTERN.test(value)) {
    return [{ path: 'date', message: 'must use YYYY-MM-DD format' }];
  }
  const [year, month, day] = value.split('-').map(Number);
  const date = new Date(Date.UTC(year, month - 1, day));
  if (
    date.getUTCFullYear() !== year ||
    date.getUTCMonth() !== month - 1 ||
    date.getUTCDate() !== day
  ) {
    return [{ path: 'date', message: 'must be a real calendar date' }];
  }
  return [];
}

function validateTimezone(value: unknown): ValidationIssue[] {
  if (typeof value !== 'string' || !TIMEZONE_PATTERN.test(value)) {
    return [{ path: 'timezone', message: 'must be an IANA timezone such as Australia/Melbourne' }];
  }
  try {
    new Intl.DateTimeFormat('en-AU', { timeZone: value }).format();
  } catch {
    return [{ path: 'timezone', message: 'must be a supported IANA timezone' }];
  }
  return [];
}

export function validateHealthBridgeSummary(value: unknown): {
  issues: ValidationIssue[];
  summary?: HealthBridgeSummary;
} {
  if (!isRecord(value)) {
    return { issues: [{ path: '', message: 'body must be a JSON object' }] };
  }

  const issues = unknownFields(value, TOP_LEVEL_FIELDS, '');
  if (value.schema_version !== SUPPORTED_SCHEMA_VERSION) {
    issues.push({ path: 'schema_version', message: `must be ${SUPPORTED_SCHEMA_VERSION}` });
  }
  issues.push(...validateDate(value.date));
  issues.push(...validateTimezone(value.timezone));

  if (value.activity !== undefined) {
    if (!isRecord(value.activity)) issues.push({ path: 'activity', message: 'must be an object' });
    else {
      issues.push(...unknownFields(value.activity, ACTIVITY_FIELDS, 'activity'));
      if (value.activity.steps !== undefined) issues.push(...numberInRange(value.activity.steps, 'activity.steps', 0, 200_000, true));
      if (value.activity.walking_distance_km !== undefined) issues.push(...numberInRange(value.activity.walking_distance_km, 'activity.walking_distance_km', 0, 200));
    }
  }

  if (value.recovery !== undefined) {
    if (!isRecord(value.recovery)) issues.push({ path: 'recovery', message: 'must be an object' });
    else {
      issues.push(...unknownFields(value.recovery, RECOVERY_FIELDS, 'recovery'));
      if (value.recovery.resting_heart_rate_bpm !== undefined) issues.push(...numberInRange(value.recovery.resting_heart_rate_bpm, 'recovery.resting_heart_rate_bpm', 20, 240));
      if (value.recovery.hrv_sdnn_ms !== undefined) issues.push(...numberInRange(value.recovery.hrv_sdnn_ms, 'recovery.hrv_sdnn_ms', 0, 5_000));
    }
  }

  if (value.sleep !== undefined) {
    if (!isRecord(value.sleep)) issues.push({ path: 'sleep', message: 'must be an object' });
    else {
      issues.push(...unknownFields(value.sleep, SLEEP_FIELDS, 'sleep'));
      if (value.sleep.duration_minutes !== undefined) issues.push(...numberInRange(value.sleep.duration_minutes, 'sleep.duration_minutes', 0, 1_440));
      if (value.sleep.source !== undefined && value.sleep.source !== 'healthkit' && value.sleep.source !== 'manual') {
        issues.push({ path: 'sleep.source', message: 'must be healthkit or manual' });
      }
    }
  }

  if (value.workouts !== undefined) {
    if (!Array.isArray(value.workouts)) issues.push({ path: 'workouts', message: 'must be an array' });
    else if (value.workouts.length > 50) issues.push({ path: 'workouts', message: 'must contain at most 50 items' });
    else value.workouts.forEach((workout, index) => {
      const path = `workouts[${index}]`;
      if (!isRecord(workout)) {
        issues.push({ path, message: 'must be an object' });
        return;
      }
      issues.push(...unknownFields(workout, WORKOUT_FIELDS, path));
      if (workout.duration_minutes === undefined) issues.push({ path: `${path}.duration_minutes`, message: 'is required' });
      else issues.push(...numberInRange(workout.duration_minutes, `${path}.duration_minutes`, 0, 1_440));
      if (workout.type !== undefined && (typeof workout.type !== 'string' || workout.type.length === 0 || workout.type.length > 80)) {
        issues.push({ path: `${path}.type`, message: 'must be a non-empty string of at most 80 characters' });
      }
    });
  }

  if (value.quality !== undefined) {
    if (!isRecord(value.quality)) issues.push({ path: 'quality', message: 'must be an object' });
    else {
      issues.push(...unknownFields(value.quality, QUALITY_FIELDS, 'quality'));
      for (const [key, quality] of Object.entries(value.quality)) {
        if (typeof quality !== 'string' || !QUALITY_VALUES.has(quality)) {
          issues.push({ path: `quality.${key}`, message: 'must be unavailable, not_collected, partial, valid, or corrected' });
        }
      }
    }
  }

  return issues.length ? { issues } : { issues: [], summary: value as unknown as HealthBridgeSummary };
}

function canonicalize(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(canonicalize);
  if (isRecord(value)) {
    return Object.fromEntries(Object.keys(value).sort().map((key) => [key, canonicalize(value[key])]));
  }
  return value;
}

export function canonicalJson(value: unknown): string {
  return JSON.stringify(canonicalize(value));
}

export async function sha256Hex(value: string): Promise<string> {
  const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(value));
  return Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, '0')).join('');
}
