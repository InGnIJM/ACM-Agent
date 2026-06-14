// ============================================================
// Pagination state hook — keeps page / limit / total in sync
// with data-fetching components.
// ============================================================

import { useState, useCallback } from "react";

export interface UsePaginationReturn {
  page: number;
  limit: number;
  total: number;
  setPage: (p: number) => void;
  setLimit: (l: number) => void;
  setTotal: (t: number) => void;
  /** Convenience: resets to page 1 (e.g. after filter change). */
  reset: () => void;
}

export default function usePagination(
  initialPage = 1,
  initialLimit = 20,
): UsePaginationReturn {
  const [page, setPage] = useState(initialPage);
  const [limit, setLimit] = useState(initialLimit);
  const [total, setTotal] = useState(0);

  const handleSetPage = useCallback((p: number) => setPage(p), []);
  const handleSetLimit = useCallback((l: number) => {
    setLimit(l);
    setPage(1); // Reset to first page when page size changes
  }, []);
  const handleSetTotal = useCallback((t: number) => setTotal(t), []);
  const reset = useCallback(() => setPage(1), []);

  return {
    page,
    limit,
    total,
    setPage: handleSetPage,
    setLimit: handleSetLimit,
    setTotal: handleSetTotal,
    reset,
  };
}
