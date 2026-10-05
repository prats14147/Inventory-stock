import { useMemo, useState } from "react";
import { useWatchlist } from "../hooks/useWatchlist";

interface Props {
  productId: string;
  variant?: "icon" | "full";
  className?: string;

  // Inventory row-specific favorite state
  rowKey?: string;
  selectedRowKey?: string | null;
  onRowSelected?: (
    rowKey: string | null
  ) => void;
}

export default function PinButton({
  productId,
  variant = "icon",
  className = "",
  rowKey,
  selectedRowKey = null,
  onRowSelected,
}: Props) {
  const {
    isPinned,
    toggle,
  } = useWatchlist();

  const [busy, setBusy] =
    useState(false);

  const productPinned =
    isPinned(productId);

  const hasRowSelection =
    rowKey !== undefined;

  /*
   * Outside Inventory:
   *   pinned = backend watchlist state.
   *
   * Inside Inventory:
   *   pinned = backend product is pinned AND
   *            this exact row is the selected row.
   */
  const pinned = useMemo(() => {
    if (!hasRowSelection) {
      return productPinned;
    }

    return (
      productPinned &&
      selectedRowKey === rowKey
    );
  }, [
    hasRowSelection,
    productPinned,
    selectedRowKey,
    rowKey,
  ]);

  async function handleClick() {
    if (busy) {
      return;
    }

    /*
     * Normal product-level PinButton
     * used outside Inventory.
     */
    if (
      !hasRowSelection ||
      !rowKey
    ) {
      try {
        setBusy(true);
        await toggle(productId);
      } finally {
        setBusy(false);
      }

      return;
    }

    /*
     * Product is not yet in the backend watchlist.
     *
     * Select this exact Inventory row and
     * add the product to the watchlist.
     */
    if (!productPinned) {
      onRowSelected?.(rowKey);

      try {
        setBusy(true);
        await toggle(productId);
      } finally {
        setBusy(false);
      }

      return;
    }

    /*
     * Product is already pinned and this exact
     * row is currently selected.
     *
     * Clicking again removes the product from
     * the backend watchlist.
     */
    if (
      selectedRowKey === rowKey
    ) {
      onRowSelected?.(null);

      try {
        setBusy(true);
        await toggle(productId);
      } finally {
        setBusy(false);
      }

      return;
    }

    /*
     * Product is already pinned, but another
     * Inventory row for the same product was clicked.
     *
     * Move the visual star only.
     *
     * DO NOT call toggle() here.
     */
    onRowSelected?.(rowKey);
  }

  const buttonLabel = pinned
    ? `Remove ${productId} from favorites`
    : `Add ${productId} to favorites`;

  if (variant === "full") {
    return (
      <button
        type="button"
        onClick={handleClick}
        disabled={busy}
        aria-label={buttonLabel}
        aria-pressed={pinned}
        className={`inline-flex items-center gap-2 rounded-lg border px-3 py-2 text-sm font-medium transition ${
          pinned
            ? "border-amber-300 bg-amber-50 text-amber-700 hover:bg-amber-100"
            : "border-gray-300 bg-white text-gray-600 hover:bg-gray-50"
        } disabled:cursor-not-allowed disabled:opacity-50 ${className}`}
      >
        <span
          aria-hidden="true"
          className="text-lg leading-none"
        >
          {pinned ? "★" : "☆"}
        </span>

        <span>
          {pinned
            ? "Favorited"
            : "Favorite"}
        </span>
      </button>
    );
  }

  return (
    <button
      type="button"
      onClick={handleClick}
      disabled={busy}
      aria-label={buttonLabel}
      aria-pressed={pinned}
      title={
        pinned
          ? "Remove from favorites"
          : "Add to favorites"
      }
      className={`inline-flex h-8 w-8 items-center justify-center rounded-md transition hover:bg-amber-50 disabled:cursor-not-allowed disabled:opacity-50 ${className}`}
    >
      <span
        aria-hidden="true"
        className={`text-xl leading-none ${
          pinned
            ? "text-amber-500"
            : "text-gray-400 hover:text-amber-500"
        }`}
      >
        {pinned ? "★" : "☆"}
      </span>
    </button>
  );
}