// frontend/src/hooks/useWatchlist.ts
//
// One shared source of truth for "which products are pinned". A pin can be
// toggled from the Stockout grid, the Inventory table, a chat answer card, and
// the Watchlist page itself -- all of them have to agree the instant a pin
// changes, so the state lives in a module-level store with subscribers rather
// than in each component's own useState.

import { useCallback, useEffect, useState } from "react";
import { ApiError, getWatchlistIds, pinProduct, unpinProduct } from "../services/api";

type Listener = (ids: string[]) => void;

let ids: string[] = [];
let loaded = false;
let inflight: Promise<void> | null = null;
let error: string | null = null;
const listeners = new Set<Listener>();
// Product ids currently mid-request, so double-clicks can't double-post.
const pending = new Set<string>();

function emit(next: string[]) {
  ids = next;
  listeners.forEach((fn) => fn(ids));
}

function ensureLoaded(): Promise<void> {
  if (loaded) return Promise.resolve();
  if (inflight) return inflight;
  inflight = getWatchlistIds()
    .then((res) => {
      ids = res.product_ids;
      error = null;
    })
    .catch((err) => {
      error = err instanceof ApiError ? err.message : "Could not load your watchlist.";
    })
    .finally(() => {
      loaded = true;
      inflight = null;
      emit(ids);
    });
  return inflight;
}

export interface WatchlistState {
  ids: string[];
  isPinned: (productId: string) => boolean;
  toggle: (productId: string) => Promise<void>;
  busy: (productId: string) => boolean;
  loading: boolean;
  error: string | null;
  /** Re-reads from the API (after a simulator tick changes the data, say). */
  refresh: () => Promise<void>;
}

export function useWatchlist(): WatchlistState {
  const [localIds, setLocalIds] = useState<string[]>(ids);
  const [loading, setLoading] = useState(!loaded);
  const [localError, setLocalError] = useState<string | null>(error);
  const [, forceRender] = useState(0);

  useEffect(() => {
    const listener: Listener = (next) => {
      setLocalIds(next);
      setLocalError(error);
      forceRender((n) => n + 1);
    };
    listeners.add(listener);
    void ensureLoaded().then(() => {
      setLocalIds(ids);
      setLocalError(error);
      setLoading(false);
    });
    return () => {
      listeners.delete(listener);
    };
  }, []);

  const refresh = useCallback(async () => {
    loaded = false;
    setLoading(true);
    await ensureLoaded();
    setLocalError(error);
    setLoading(false);
  }, []);

  const toggle = useCallback(async (productId: string) => {
    if (pending.has(productId)) return;
    pending.add(productId);
    forceRender((n) => n + 1);
    const wasPinned = ids.includes(productId);
    // Optimistic: the button flips immediately, and reverts if the call fails.
    emit(wasPinned ? ids.filter((id) => id !== productId) : [...ids, productId]);
    try {
      if (wasPinned) await unpinProduct(productId);
      else await pinProduct(productId);
      error = null;
    } catch (err) {
      emit(wasPinned ? [...ids, productId] : ids.filter((id) => id !== productId));
      error = err instanceof ApiError ? err.message : "That change did not save. Please try again.";
      setLocalError(error);
    } finally {
      pending.delete(productId);
      emit(ids);
      forceRender((n) => n + 1);
    }
  }, []);

  // `toggle` calls forceRender, so `busy()` is always re-read after a click.
  return {
    ids: localIds,
    isPinned: (productId) => localIds.includes(productId),
    toggle,
    busy: (productId) => pending.has(productId),
    loading,
    error: localError,
    refresh,
  };
}