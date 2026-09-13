'use client';

import { Badge, Button } from '@/components/ui';
import { STATUSES, type ShoppingListItem } from '@/lib/shoppingList';

const STATUS_TONE: Record<ShoppingListItem['status'], Parameters<typeof Badge>[0]['status']> = {
  wishlist: 'neutral',
  saved_for: 'info',
  purchased: 'success',
  cancelled: 'error',
};

function statusLabel(status: ShoppingListItem['status']): string {
  return STATUSES.find((s) => s.key === status)?.label ?? status;
}

/** One row in the reorderable list — plain HTML5 drag-and-drop (no dnd
 * library in this repo to reuse, and none exists here to add one for).
 * draggable/onDragStart/onDragOver/onDrop are native browser behaviour. */
export function ItemRow({
  item,
  draggable = true,
  onDragStart,
  onDragOver,
  onDrop,
  onEdit,
  onMarkPurchased,
  onDelete,
}: {
  item: ShoppingListItem;
  draggable?: boolean;
  onDragStart: () => void;
  onDragOver: (e: React.DragEvent) => void;
  onDrop: () => void;
  onEdit: () => void;
  onMarkPurchased: () => void;
  onDelete: () => void;
}) {
  return (
    <div
      draggable={draggable}
      onDragStart={draggable ? onDragStart : undefined}
      onDragOver={draggable ? onDragOver : undefined}
      onDrop={draggable ? onDrop : undefined}
      className="flex flex-wrap items-center gap-3 rounded-md border border-wb-line bg-wb-surface p-3"
    >
      <span
        aria-hidden
        className={`select-none text-wb-ink2 ${draggable ? 'cursor-grab' : 'opacity-30'}`}
        title={draggable ? 'Drag to reorder' : 'Clear filters to reorder'}
      >
        ⠿
      </span>

      {item.image_url ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img src={item.image_url} alt="" className="h-12 w-12 shrink-0 rounded object-cover" />
      ) : (
        <div className="h-12 w-12 shrink-0 rounded bg-wb-surface-raised" />
      )}

      <div className="min-w-0 flex-1 basis-40">
        <div className="flex items-start justify-between gap-2">
          <span className="break-words text-[14px] font-medium text-wb-ink">{item.product_name}</span>
          <span className="shrink-0 text-[13px] font-medium text-wb-ink">
            {item.currency} {item.cost.toFixed(2)}
          </span>
        </div>
        <div className="mt-1 flex flex-wrap items-center gap-2 text-[11px] text-wb-ink2">
          {item.vendor && <span>{item.vendor}</span>}
          <span>{item.category}</span>
          {item.recipient && <span>For: {item.recipient}</span>}
          {item.target_occasion && <span>{item.target_occasion}</span>}
        </div>
      </div>

      <Badge status={STATUS_TONE[item.status]}>{statusLabel(item.status)}</Badge>

      <div className="flex w-full shrink-0 flex-wrap items-center gap-1.5 sm:w-auto sm:justify-end">
        {item.status !== 'purchased' && (
          <Button size="sm" variant="secondary" onClick={onMarkPurchased}>Mark purchased</Button>
        )}
        <Button size="sm" variant="ghost" onClick={onEdit}>Edit</Button>
        <Button size="sm" variant="ghost" onClick={onDelete}>Delete</Button>
      </div>
    </div>
  );
}
