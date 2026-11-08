import * as path from 'path';
import { describe, expect, it } from 'vitest';
import { MISSION_REGISTRY_ENV, resolveMissionRegistryPath } from './mission-registry-path';

const REPO = path.resolve('/srv/repo');
const TRACKED = path.join(REPO, 'core', 'mission-control', 'registry', 'mission-index.txt');

describe('resolveMissionRegistryPath', () => {
  it('defaults to the tracked checkout path when the env var is unset', () => {
    expect(resolveMissionRegistryPath(REPO, {})).toBe(TRACKED);
  });

  it('treats a blank env value as unset', () => {
    expect(resolveMissionRegistryPath(REPO, { [MISSION_REGISTRY_ENV]: '   ' })).toBe(TRACKED);
  });

  it('honours an absolute external override', () => {
    const external = path.resolve('/var/lib/starship/mission-index.txt');
    expect(resolveMissionRegistryPath(REPO, { [MISSION_REGISTRY_ENV]: external })).toBe(external);
  });

  it('rejects a relative override so the result never depends on cwd', () => {
    expect(() =>
      resolveMissionRegistryPath(REPO, { [MISSION_REGISTRY_ENV]: 'mission-index.txt' }),
    ).toThrow(/absolute path/);
  });
});
