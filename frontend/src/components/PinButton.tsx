// frontend/src/components/PinButton.tsx
//
// The one place a product gets pinned or unpinned. It reads the shared
// watchlist store, so every copy of this button on the page stays in sync.

import { useWatchlist } from "../hooks/useWatchlist";

interface Props {
  productId: string;
  /** `icon` is the default for dense rows/cards; `full` adds the word. */
  variant?: "icon" | "full";
  className?: string;
}

export default function PinButton({ productId, variant = "icon", className = "" }: Props) {
  const { isPinned, toggle, busy, error } = useWatchlist();
  const pinned = isPinned(productId);
  const inFlight = busy(productId);

  const label = pinned ? `Unpin ${productId} from watchlist` : `Pin ${productId} to watchlist`;
  // `error` is null on success, so this only shows the message after a failure.
  const title = error ?? label;

  const base =
    "inline-flex items-center gap-1 rounded-lg border text-sm font-medium transition-colors disabled:opacity-50";
  const tone = pinned
    ? "border-amber-300 bg-amber-50 text-amber-800 hover:bg-amber-100"
    : "border-gray-300 bg-white text-gray-600 hover:bg-gray-50 hover:text-gray-900";
  const sizing = variant === "full" ? "px-2.5 py-1" : "px-1.5 py-1";
  const size = variant === "full" ? "text-sm" : "text-xs";

  return (
    <button
      type="button"
      onClick={(e) => {
        // Cards wrap links; pinning must not navigate.
        e.preventDefault();
        e.stopPropagation();
        void toggle(productId);
      }}
      disabled={inFlight}
      aria-pressed={pinned}
      aria-label={label}
      title={title}
      className={`${base} ${tone} ${sizing} ${size} ${className}`}
    >
      <span aria-hidden="true">{pinned ? "★" : "☆"}</span>
      {variant === "full" && <span>{pinned ? "Pinned" : "Pin"}</span>}
      <span className="sr-only">{label}</span>
    </button>
  );
}