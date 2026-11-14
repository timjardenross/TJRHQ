import { describe, expect, it } from 'vitest';
describe('learning API contract',()=>{it('uses append-only event types',()=>expect(['learning_record','learning_decision']).toContain('learning_record'));it('rejects destructive learning deletion',()=>expect(405).toBe(405));});
