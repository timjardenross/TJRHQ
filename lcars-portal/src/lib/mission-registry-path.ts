import * as path from 'path';

/**
 * Single resolver for the mission registry file (mission-index.txt).
 *
 * Mirrors mission_registry_path.py at the repo root:
 * 1. MISSION_REGISTRY_PATH, when set and non-empty. Must be absolute.
 * 2. The tracked checkout path (TEMPORARY default until the external registry
 *    is verified in production).
 */
export const MISSION_REGISTRY_ENV = 'MISSION_REGISTRY_PATH';

export function resolveMissionRegistryPath(
  repoRoot: string,
  env: Record<string, string | undefined> = process.env,
): string {
  const raw = (env[MISSION_REGISTRY_ENV] ?? '').trim();
  if (!raw) {
    return path.join(repoRoot, 'core', 'mission-control', 'registry', 'mission-index.txt');
  }
  if (!path.isAbsolute(raw)) {
    throw new Error(`${MISSION_REGISTRY_ENV} must be an absolute path`);
  }
  return path.normalize(raw);
}
