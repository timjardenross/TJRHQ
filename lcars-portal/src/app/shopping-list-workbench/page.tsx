'use client';

// Shopping List Workbench — a wishlist/gift-tracking CRUD list. Same
// WorkbenchShell architecture as every other workbench (see ready-room/
// page.tsx). Single-Captain, single-tenant: no budget/pay-cycle modeling,
// no recurring-payment logic, no cross-currency conversion (deliberately
// out of scope for v1 — see migration 0199's header comment).

import { useEffect, useMemo, useRef, useState } from 'react';
import { ShoppingCart, Receipt, Heart } from 'lucide-react';
import { WorkbenchShell, Button, Card, Select } from '@/components/ui';
import {
  fetchShoppingList,
  createShoppingListItem,
  updateShoppingListItem,
  deleteShoppingListItem,
  markPurchased,
  reorderShoppingList,
  subtotalsByCurrency,
  STATUSES,
  type ShoppingListItem,
  type NewShoppingListItemInput,
  type ShoppingListResult,
} from '@/lib/shoppingList';
import { ItemFormModal } from './_components/ItemFormModal';
import { ItemRow } from './_components/ItemRow';

const ALL = '__all__';

export default function ShoppingListWorkbench() {
  const [items, setItems] = useState<ShoppingListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<ShoppingListItem | null>(null);

  const [categoryFilter, setCategoryFilter] = useState(ALL);
  const [statusFilter, setStatusFilter] = useState(ALL);
  const [recipientFilter, setRecipientFilter] = useState(ALL);
  const [occasionFilter, setOccasionFilter] = useState(ALL);

  const dragIndexRef = useRef<number | null>(null);

  async function load() {
    setLoading(true);
    setItems(await fetchShoppingList());
    setLoading(false);
  }

  useEffect(() => {
    load();
  }, []);

  const categories = useMemo(() => uniqueSorted(items.map((i) => i.category)), [items]);
  const recipients = useMemo(() => uniqueSorted(items.map((i) => i.recipient).filter(Boolean) as string[]), [items]);
  const occasions = useMemo(() => uniqueSorted(items.map((i) => i.target_occasion).filter(Boolean) as string[]), [items]);

  const filtered = useMemo(() => {
    return items.filter((i) => {
      if (categoryFilter !== ALL && i.category !== categoryFilter) return false;
      if (statusFilter !== ALL && i.status !== statusFilter) return false;
      if (recipientFilter !== ALL && (i.recipient ?? '') !== recipientFilter) return false;
      if (occasionFilter !== ALL && (i.target_occasion ?? '') !== occasionFilter) return false;
      return true;
    });
  }, [items, categoryFilter, statusFilter, recipientFilter, occasionFilter]);

  const subtotals = useMemo(() => subtotalsByCurrency(filtered), [filtered]);

  // Real, derived-from-fetched-data stats for the summary row — no field
  // here is fabricated: purchasedSubtotals/wishlistedCount are the same
  // `items` this page already loads, just filtered by status.
  const purchasedSubtotals = useMemo(
    () => subtotalsByCurrency(items.filter((i) => i.status === 'purchased')),
    [items],
  );
  const wishlistedCount = useMemo(() => items.filter((i) => i.status === 'wishlist').length, [items]);

  async function handleSave(input: NewShoppingListItemInput): Promise<ShoppingListResult> {
    const result = editing
      ? await updateShoppingListItem(editing.id, input)
      : await createShoppingListItem(input);
    if (!result.ok) return result;
    setModalOpen(false);
    setEditing(null);
    await load();
    return result;
  }

  async function handleDelete(id: string) {
    if (!confirm('Delete this item?')) return;
    await deleteShoppingListItem(id);
    await load();
  }

  async function handleMarkPurchased(id: string) {
    await markPurchased(id);
    await load();
  }

  const isFiltered = categoryFilter !== ALL || statusFilter !== ALL || recipientFilter !== ALL || occasionFilter !== ALL;

  // priority_rank is one global order across the whole list, so drag-to-
  // reorder only writes a clean result when every item is visible — while
  // any filter narrows the list, dragging is disabled rather than silently
  // reassigning ranks 1..N over just the visible subset (which would
  // collide with the hidden items' existing ranks).
  function handleDrop(targetIndex: number) {
    if (isFiltered) return;
    const sourceIndex = dragIndexRef.current;
    dragIndexRef.current = null;
    if (sourceIndex === null || sourceIndex === targetIndex) return;

    const reordered = [...items];
    const [moved] = reordered.splice(sourceIndex, 1);
    reordered.splice(targetIndex, 0, moved);

    setItems(reordered);
    reorderShoppingList(reordered.map((i) => i.id));
  }

  return (
    <WorkbenchShell
      title="Shopping List"
      eyebrow="Life Admin"
      tagline="Everything worth buying, in one place — for you or for someone else. Nothing tracked here is a bill or a subscription."
      back={{ href: '/workbenches', label: 'Workbenches' }}
      right={<Button size="sm" variant="primary" onClick={() => { setEditing(null); setModalOpen(true); }}>Add item</Button>}
      mode="command"
    >
      <div className="risk-reference-surface risk-reference-focus flex flex-col gap-4">
        <div className="risk-reference-kicker">Focus / utility · scan, decide, act</div>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
          <Card className="flex items-center gap-3 p-4">
            <ShoppingCart className="h-5 w-5 shrink-0 text-wb-sage-deep" aria-hidden />
            <div>
              <div className="text-[13px] font-semibold text-wb-ink">{items.length} item{items.length === 1 ? '' : 's'}</div>
              <div className="text-[11px] text-wb-ink2">
                {subtotals.length > 0
                  ? subtotals.map((s) => `${s.currency} ${s.total.toFixed(2)}`).join(' · ')
                  : 'No cost recorded yet'}
              </div>
            </div>
          </Card>
          <Card className="flex items-center gap-3 p-4">
            <Receipt className="h-5 w-5 shrink-0 text-state-ok-on" aria-hidden />
            <div>
              <div className="text-[13px] font-semibold text-wb-ink">
                {items.filter((i) => i.status === 'purchased').length} purchased
              </div>
              <div className="text-[11px] text-wb-ink2">
                {purchasedSubtotals.length > 0
                  ? purchasedSubtotals.map((s) => `${s.currency} ${s.total.toFixed(2)}`).join(' · ')
                  : 'Nothing purchased yet'}
              </div>
            </div>
          </Card>
          <Card className="flex items-center gap-3 p-4">
            <Heart className="h-5 w-5 shrink-0 text-wb-sand-deep" aria-hidden />
            <div>
              <div className="text-[13px] font-semibold text-wb-ink">{wishlistedCount} wishlisted</div>
              <div className="text-[11px] text-wb-ink2">Not yet saving or purchased</div>
            </div>
          </Card>
        </div>

        <Card>
          <div className="flex flex-col gap-4">
            <div className="flex flex-wrap gap-2">
              <Select aria-label="Filter by category" value={categoryFilter} onChange={(e) => setCategoryFilter(e.target.value)}>
                <option value={ALL}>All categories</option>
                {categories.map((c) => <option key={c} value={c}>{c}</option>)}
              </Select>
              <Select aria-label="Filter by status" value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
                <option value={ALL}>All statuses</option>
                {STATUSES.map((s) => <option key={s.key} value={s.key}>{s.label}</option>)}
              </Select>
              <Select aria-label="Filter by recipient" value={recipientFilter} onChange={(e) => setRecipientFilter(e.target.value)}>
                <option value={ALL}>Everyone</option>
                {recipients.map((r) => <option key={r} value={r}>{r}</option>)}
              </Select>
              <Select aria-label="Filter by occasion" value={occasionFilter} onChange={(e) => setOccasionFilter(e.target.value)}>
                <option value={ALL}>All occasions</option>
                {occasions.map((o) => <option key={o} value={o}>{o}</option>)}
              </Select>
            </div>

            {loading ? (
              <p className="text-[13px] text-wb-ink2">Loading…</p>
            ) : filtered.length === 0 ? (
              <p className="text-[13px] text-wb-ink2">Nothing here yet. Add an item to get started.</p>
            ) : (
              <div className="flex flex-col gap-2">
                {filtered.map((item, index) => (
                  <ItemRow
                    key={item.id}
                    item={item}
                    draggable={!isFiltered}
                    onDragStart={() => { dragIndexRef.current = index; }}
                    onDragOver={(e) => e.preventDefault()}
                    onDrop={() => handleDrop(index)}
                    onEdit={() => { setEditing(item); setModalOpen(true); }}
                    onMarkPurchased={() => handleMarkPurchased(item.id)}
                    onDelete={() => handleDelete(item.id)}
                  />
                ))}
              </div>
            )}
          </div>
        </Card>
      </div>

      <ItemFormModal
        open={modalOpen}
        onClose={() => { setModalOpen(false); setEditing(null); }}
        onSave={handleSave}
        initial={editing}
      />
    </WorkbenchShell>
  );
}

function uniqueSorted(values: string[]): string[] {
  return Array.from(new Set(values)).sort((a, b) => a.localeCompare(b));
}
