import { describe, expect, it } from 'vitest';
import { resolveSiteUrl } from '../lib/site';

describe('resolveSiteUrl', () => {
  it('uses an explicit NEXT_PUBLIC_SITE_URL first, without a trailing slash', () => {
    expect(resolveSiteUrl({ NEXT_PUBLIC_SITE_URL: 'https://hq.example.com/', VERCEL_ENV: 'production', VERCEL_PROJECT_PRODUCTION_URL: 'p.vercel.app', VERCEL_URL: 'd.vercel.app' })).toBe('https://hq.example.com');
  });
  it('on production uses the stable production domain, not the per-deployment URL', () => {
    expect(resolveSiteUrl({ VERCEL_ENV: 'production', VERCEL_PROJECT_PRODUCTION_URL: 'usstjros.vercel.app', VERCEL_URL: 'usstjros-abc123-usstjr.vercel.app' })).toBe('https://usstjros.vercel.app');
  });
  it('on a preview keeps the preview deployment URL', () => {
    expect(resolveSiteUrl({ VERCEL_ENV: 'preview', VERCEL_PROJECT_PRODUCTION_URL: 'usstjros.vercel.app', VERCEL_URL: 'usstjros-git-x-usstjr.vercel.app' })).toBe('https://usstjros-git-x-usstjr.vercel.app');
  });
  it('falls back to the deployment URL, then localhost', () => {
    expect(resolveSiteUrl({ VERCEL_URL: 'd.vercel.app' })).toBe('https://d.vercel.app');
    expect(resolveSiteUrl({})).toBe('http://localhost:3100');
  });
});
