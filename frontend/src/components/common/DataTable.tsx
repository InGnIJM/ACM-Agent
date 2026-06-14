import { type ReactNode } from "react";
import {
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  TablePagination,
  TableSortLabel,
  Paper,
  Box,
  Skeleton,
  Typography,
} from "@mui/material";
import LoadingSpinner from "./LoadingSpinner";
import EmptyState from "./EmptyState";

// ============================================================
// Types
// ============================================================

export interface ColumnDef<T> {
  key: string;
  header: string;
  render?: (row: T) => ReactNode;
  sortable?: boolean;
  width?: number | string;
  align?: "left" | "center" | "right";
}

export interface PaginationState {
  page: number;
  limit: number;
  total: number;
}

export type SortDirection = "asc" | "desc";

export interface SortState {
  field: string;
  direction: SortDirection;
}

export interface DataTableProps<T> {
  columns: ColumnDef<T>[];
  data: T[];
  loading?: boolean;
  pagination?: PaginationState;
  onPageChange?: (page: number) => void;
  onSort?: (sort: SortState) => void;
  onRowClick?: (row: T) => void;
  sort?: SortState | null;
  getRowId?: (row: T) => string | number;
  emptyMessage?: string;
  dense?: boolean;
  stickyHeader?: boolean;
}

// ============================================================
// Component
// ============================================================

function DataTable<T>({
  columns,
  data,
  loading = false,
  pagination,
  onPageChange,
  onSort,
  onRowClick,
  sort = null,
  getRowId,
  emptyMessage = "No data found",
  dense = false,
  stickyHeader = false,
}: DataTableProps<T>) {
  // ---- handlers ----

  const handleSort = (field: string) => {
    if (!onSort) return;
    const newDirection: SortDirection =
      sort && sort.field === field && sort.direction === "asc" ? "desc" : "asc";
    onSort({ field, direction: newDirection });
  };

  const handlePageChange = (_event: unknown, newPage: number) => {
    onPageChange?.(newPage);
  };

  // ---- render helpers ----

  const renderLoadingRows = () =>
    Array.from({ length: pagination?.limit ?? 5 }).map((_, i) => (
      <TableRow key={`skeleton-${i}`}>
        {columns.map((col) => (
          <TableCell key={col.key} align={col.align ?? "left"}>
            <Skeleton variant="text" />
          </TableCell>
        ))}
      </TableRow>
    ));

  const renderEmpty = () => (
    <TableRow>
      <TableCell colSpan={columns.length} align="center">
        <Box py={6}>
          <EmptyState message={emptyMessage} />
        </Box>
      </TableCell>
    </TableRow>
  );

  // ---- loading state ----

  if (loading && data.length === 0) {
    return (
      <Box display="flex" justifyContent="center" py={6}>
        <LoadingSpinner message="Loading data..." />
      </Box>
    );
  }

  // ---- main render ----

  return (
    <Paper variant="outlined" sx={{ width: "100%", overflow: "hidden" }}>
      <TableContainer>
        <Table size={dense ? "small" : "medium"} stickyHeader={stickyHeader}>
          <TableHead>
            <TableRow>
              {columns.map((col) => (
                <TableCell
                  key={col.key}
                  align={col.align ?? "left"}
                  sortDirection={
                    sort?.field === col.key ? sort.direction : false
                  }
                  sx={{
                    fontWeight: 600,
                    whiteSpace: "nowrap",
                    width: col.width,
                  }}
                >
                  {col.sortable && onSort ? (
                    <TableSortLabel
                      active={sort?.field === col.key}
                      direction={
                        sort?.field === col.key ? sort.direction : "asc"
                      }
                      onClick={() => handleSort(col.key)}
                    >
                      {col.header}
                    </TableSortLabel>
                  ) : (
                    col.header
                  )}
                </TableCell>
              ))}
            </TableRow>
          </TableHead>

          <TableBody>
            {loading && data.length > 0
              ? renderLoadingRows()
              : data.length === 0
                ? renderEmpty()
                : data.map((row, idx) => (
                    <TableRow
                      key={getRowId?.(row) ?? idx}
                      hover={!!onRowClick}
                      onClick={() => onRowClick?.(row)}
                      sx={{
                        cursor: onRowClick ? "pointer" : "default",
                      }}
                    >
                      {columns.map((col) => (
                        <TableCell key={col.key} align={col.align ?? "left"}>
                          {col.render
                            ? col.render(row)
                            : String(
                                (row as Record<string, unknown>)[col.key] ?? ""
                              )}
                        </TableCell>
                      ))}
                    </TableRow>
                  ))}
          </TableBody>
        </Table>
      </TableContainer>

      {pagination && onPageChange && (
        <TablePagination
          component="div"
          count={pagination.total}
          page={pagination.page}
          rowsPerPage={pagination.limit}
          onPageChange={handlePageChange}
          rowsPerPageOptions={[pagination.limit]}
          showFirstButton
          showLastButton
        />
      )}
    </Paper>
  );
}

export default DataTable;
