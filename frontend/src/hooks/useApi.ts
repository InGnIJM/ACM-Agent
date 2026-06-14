// ============================================================
// Generic data-fetching hook — wraps any async fetcher function
// and exposes { data, loading, error, refetch }.
// ============================================================

import { useState, useEffect, useCallback, useRef } from "react";

export interface UseApiReturn<T> {
  data: T | null;
  loading: boolean;
  error: string | null;
  refetch: () => void;
}

export default function useApi<T>(
  fetcher: () => Promise<T>,
  deps: unknown[] = [],
): UseApiReturn<T> {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Track mount state to avoid setting state on unmounted component
  const mountedRef = useRef(true);

  const fetch = useCallback(() => {
    setLoading(true);
    setError(null);

    fetcher()
      .then((result) => {
        if (mountedRef.current) {
          setData(result);
        }
      })
      .catch((err: unknown) => {
        if (mountedRef.current) {
          const message =
            err instanceof Error ? err.message : String(err);
          setError(message);
        }
      })
      .finally(() => {
        if (mountedRef.current) {
          setLoading(false);
        }
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  useEffect(() => {
    mountedRef.current = true;
    fetch();
    return () => {
      mountedRef.current = false;
    };
  }, [fetch]);

  return { data, loading, error, refetch: fetch };
}
