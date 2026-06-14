// ============================================================
// Shared API types
// ============================================================

/** Wraps every list endpoint response. */
export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
}

/** Structured error shape returned by the API. */
export interface ApiError {
  status_code: number;
  detail: string;
  errors?: Record<string, string[]>;
}

/** Common query params accepted by list endpoints. */
export interface ListQuery {
  page?: number;
  page_size?: number;
  sort_by?: string;
  order?: "asc" | "desc";
}
