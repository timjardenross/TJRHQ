'use client';

import { useEffect, useState } from 'react';
import { Modal, Button, Input, Textarea, Select } from '@/components/ui';
import { previewShoppingListUrl, STATUSES, type NewShoppingListItemInput, type ShoppingListItem } from '@/lib/shoppingList';

/** Add/edit form for one shopping list item. Paste-a-URL is an assist, not
 * a requirement — "Fetch details" pre-fills the fields below via
 * /api/shopping-list/preview, but every field stays directly editable and
 * a blank source_url is a fully valid, fully manual entry. */
export function ItemFormModal({
  open,
  onClose,
  onSave,
  initial,
}: {
  open: boolean;
  onClose: () => void;
  onSave: (input: NewShoppingListItemInput) => Promise<void>;
  initial?: ShoppingListItem | null;
}) {
  const [sourceUrl, setSourceUrl] = useState('');
  const [productName, setProductName] = useState('');
  const [vendor, setVendor] = useState('');
  const [imageUrl, setImageUrl] = useState('');
  const [cost, setCost] = useState('');
  const [currency, setCurrency] = useState('AUD');
  const [category, setCategory] = useState('');
  const [recipient, setRecipient] = useState('');
  const [targetOccasion, setTargetOccasion] = useState('');
  const [status, setStatus] = useState<NewShoppingListItemInput['status']>('wishlist');
  const [notes, setNotes] = useState('');
  const [fetching, setFetching] = useState(false);
  const [fetchError, setFetchError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!open) return;
    setSourceUrl(initial?.source_url ?? '');
    setProductName(initial?.product_name ?? '');
    setVendor(initial?.vendor ?? '');
    setImageUrl(initial?.image_url ?? '');
    setCost(initial ? String(initial.cost) : '');
    setCurrency(initial?.currency ?? 'AUD');
    setCategory(initial?.category ?? '');
    setRecipient(initial?.recipient ?? '');
    setTargetOccasion(initial?.target_occasion ?? '');
    setStatus(initial?.status ?? 'wishlist');
    setNotes(initial?.notes ?? '');
    setFetchError(null);
  }, [open, initial]);

  async function fetchDetails() {
    if (!sourceUrl.trim()) return;
    setFetching(true);
    setFetchError(null);
    const result = await previewShoppingListUrl(sourceUrl.trim());
    setFetching(false);
    if (!result.ok || !result.draft) {
      setFetchError(result.error ?? 'Could not fetch details from that URL.');
      return;
    }
    const { draft } = result;
    if (draft.product_name) setProductName(draft.product_name);
    if (draft.image_url) setImageUrl(draft.image_url);
    if (draft.cost !== null) setCost(String(draft.cost));
    if (draft.currency) setCurrency(draft.currency);
    if (draft.vendor) setVendor(draft.vendor);
  }

  async function handleSave() {
    setSaving(true);
    await onSave({
      product_name: productName.trim(),
      vendor: vendor.trim() || null,
      image_url: imageUrl.trim() || null,
      source_url: sourceUrl.trim() || null,
      cost: Number(cost),
      currency: currency.trim() || 'AUD',
      category: category.trim(),
      recipient: recipient.trim() || null,
      status,
      target_occasion: targetOccasion.trim() || null,
      notes: notes.trim() || null,
    });
    setSaving(false);
  }

  const canSave = productName.trim() !== '' && category.trim() !== '' && cost !== '' && Number.isFinite(Number(cost));

  return (
    <Modal open={open} onClose={onClose} title={initial ? 'Edit item' : 'Add item'}>
      <div className="flex flex-col gap-3">
        <div className="flex items-end gap-2">
          <div className="flex-1">
            <Input
              label="Product page link (optional)"
              placeholder="https://…"
              value={sourceUrl}
              onChange={(e) => setSourceUrl(e.target.value)}
            />
          </div>
          <Button size="sm" variant="secondary" disabled={!sourceUrl.trim() || fetching} onClick={fetchDetails}>
            {fetching ? 'Fetching…' : 'Fetch details'}
          </Button>
        </div>
        {fetchError && <p className="text-[12px] text-wb-crit">{fetchError}</p>}

        <Input label="Product name" value={productName} onChange={(e) => setProductName(e.target.value)} required />

        <div className="flex gap-2">
          <div className="flex-1">
            <Input label="Cost" type="number" step="0.01" value={cost} onChange={(e) => setCost(e.target.value)} required />
          </div>
          <div className="w-24">
            <Input label="Currency" value={currency} onChange={(e) => setCurrency(e.target.value.toUpperCase())} maxLength={3} />
          </div>
        </div>

        <div className="flex gap-2">
          <div className="flex-1">
            <Input label="Vendor" value={vendor} onChange={(e) => setVendor(e.target.value)} />
          </div>
          <div className="flex-1">
            <Input label="Category" value={category} onChange={(e) => setCategory(e.target.value)} placeholder="e.g. electronics" required />
          </div>
        </div>

        <div className="flex gap-2">
          <div className="flex-1">
            <Input label="Who's it for" value={recipient} onChange={(e) => setRecipient(e.target.value)} placeholder="Leave blank for yourself" />
          </div>
          <div className="flex-1">
            <Input label="Target occasion" value={targetOccasion} onChange={(e) => setTargetOccasion(e.target.value)} placeholder="e.g. Christmas 2026" />
          </div>
        </div>

        <Input label="Image URL" value={imageUrl} onChange={(e) => setImageUrl(e.target.value)} />

        <Select label="Status" value={status} onChange={(e) => setStatus(e.target.value as NewShoppingListItemInput['status'])}>
          {STATUSES.map((s) => <option key={s.key} value={s.key}>{s.label}</option>)}
        </Select>

        <Textarea label="Notes" rows={2} value={notes} onChange={(e) => setNotes(e.target.value)} />

        <div className="mt-2 flex justify-end gap-2">
          <Button variant="ghost" onClick={onClose} disabled={saving}>Cancel</Button>
          <Button variant="primary" onClick={handleSave} disabled={!canSave || saving}>
            {saving ? 'Saving…' : 'Save'}
          </Button>
        </div>
      </div>
    </Modal>
  );
}
