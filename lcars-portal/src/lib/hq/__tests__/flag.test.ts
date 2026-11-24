import { describe, expect, it } from 'vitest';
import { isHqEnabled } from '../flag';

describe('HQ_WORKBENCH_ENABLED', () => {
  it('is off by default', () => {
    expect(isHqEnabled({})).toBe(false);
    expect(isHqEnabled({ HQ_WORKBENCH_ENABLED: undefined })).toBe(false);
    expect(isHqEnabled({ HQ_WORKBENCH_ENABLED: '' })).toBe(false);
  });
  it('is on only for explicit truthy values', () => {
    for (const v of ['1', 'true', 'TRUE', ' yes ', 'on']) expect(isHqEnabled({ HQ_WORKBENCH_ENABLED: v })).toBe(true);
  });
  it('stays off for anything else', () => {
    for (const v of ['0', 'false', 'off', 'no', 'enabled', 'y']) expect(isHqEnabled({ HQ_WORKBENCH_ENABLED: v })).toBe(false);
  });
});
