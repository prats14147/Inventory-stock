// frontend/src/hooks/useApi.ts

import { useEffect, useState } from "react";
import { API_BASE_URL, ApiError } from "../services/api";

interface UseApiState<T> {
  data: T | null;
  loading: boolean;
  error: string | null;
}

/**
 * Runs `fetcher` once on mount (and whenever `deps` change), tracking
 * loading/error state so pages don't each reimplement this boilerplate.
 */
export function useApi<T>(fetcher: () => Promise<T>, deps: unknown[] = []): UseApiState<T> {
  const [state, setState] = useState<UseApiState<T>>({ data: null, loading: true, error: null });

  useEffect(() => {
    let cancelled = false;
    setState({ data: null, loading: true, error: null });
    fetcher()
      .then((data) => {
        if (!cancelled) setState({ data, loading: false, error: null });
      })
      .catch((err) => {
        if (!cancelled) {
          const message = err instanceof ApiError
            ? err.message
            : err instanceof TypeError
              ? `Cannot reach the InventoryAI API at ${API_BASE_URL}. Start the backend and PostgreSQL, then reload this page.`
              : "Something went wrong. Please try again.";
          setState({ data: null, loading: false, error: message });
        }
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  return state;
}
