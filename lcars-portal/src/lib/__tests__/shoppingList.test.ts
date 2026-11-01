import { describe, it, expect, vi, afterEach } from 'vitest';
import {
  subtotalsByCurrency,
  previewShoppingListUrl,
  createShoppingListItem,
  reorderShoppingList,
  type ShoppingListItem,
} from '@/lib/shoppingList';

function item(overrides: Partial<ShoppingListItem> = {}): ShoppingListItem {
  return {
    id: 'id-1',
    product_name: 'Widget',
    vendor: null,
    image_url: null,
    source_url: null,
    cost: 10,
    currency: 'AUD',
    category: 'misc',
    recipient: null,
    priority_rank: 1,
    status: 'wishlist',
    target_occasion: null,
    notes: null,
    purchased_at: null,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    ...overrides,
  };
}

describe('subtotalsByCurrency', () => {
  it('groups and sums cost by currency', () => {
    const items = [
      item({ id: '1', currency: 'AUD', cost: 10 }),
      item({ id: '2', currency: 'AUD', cost: 20 }),
      item({ id: '3', currency: 'USD', cost: 5 }),
    ];
    const result = subtotalsByCurrency(items);
    expect(result).toEqual([
      { currency: 'AUD', total: 30, count: 2 },
      { currency: 'USD', total: 5, count: 1 },
    ]);
  });

  it('excludes cancelled items from subtotals', () => {
    const items = [
      item({ id: '1', currency: 'AUD', cost: 10, status: 'cancelled' }),
      item({ id: '2', currency: 'AUD', cost: 20 }),
    ];
    expect(subtotalsByCurrency(items)).toEqual([{ currency: 'AUD', total: 20, count: 1 }]);
  });

  it('returns an empty array for no items', () => {
    expect(subtotalsByCurrency([])).toEqual([]);
  });

  it('never mixes currencies into one total', () => {
    const items = [item({ id: '1', currency: 'AUD', cost: 100 }), item({ id: '2', currency: 'JPY', cost: 1000 })];
    const result = subtotalsByCurrency(items);
    expect(result.find((r) => r.currency === 'AUD')?.total).toBe(100);
    expect(result.find((r) => r.currency === 'JPY')?.total).toBe(1000);
  });
});

describe('client fetch wrappers', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('previewShoppingListUrl posts to /api/shopping-list/preview and returns the draft', async () => {
    const draft = { product_name: 'Thing', image_url: null, cost: 9.99, currency: 'AUD', vendor: 'example.com' };
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ draft }),
    });
    vi.stubGlobal('fetch', fetchMock);

    const result = await previewShoppingListUrl('https://example.com/x');
    expect(fetchMock).toHaveBeenCalledWith('/api/shopping-list/preview', expect.objectContaining({ method: 'POST' }));
    expect(result.ok).toBe(true);
    expect(result.draft).toEqual(draft);
  });

  it('previewShoppingListUrl surfaces a server-reported error without throwing', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: false,
      status: 400,
      json: async () => ({ error: 'Only http(s) URLs are allowed.' }),
    });
    vi.stubGlobal('fetch', fetchMock);

    const result = await previewShoppingListUrl('ftp://example.com');
    expect(result.ok).toBe(false);
    expect(result.error).toBe('Only http(s) URLs are allowed.');
  });

  it('previewShoppingListUrl never throws on a network failure', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('network down')));
    const result = await previewShoppingListUrl('https://example.com');
    expect(result.ok).toBe(false);
    expect(result.error).toBe('network down');
  });

  it('createShoppingListItem posts the input and returns the new id', async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ item: { id: 'new-id' } }) });
    vi.stubGlobal('fetch', fetchMock);

    const result = await createShoppingListItem({ product_name: 'X', category: 'misc', cost: 5 });
    expect(result).toEqual({ ok: true, id: 'new-id' });
  });

  it('reorderShoppingList posts ordered_ids to the reorder endpoint', async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ ok: true }) });
    vi.stubGlobal('fetch', fetchMock);

    await reorderShoppingList(['a', 'b', 'c']);
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/shopping-list/reorder',
      expect.objectContaining({ method: 'POST', body: JSON.stringify({ ordered_ids: ['a', 'b', 'c'] }) }),
    );
  });
});
