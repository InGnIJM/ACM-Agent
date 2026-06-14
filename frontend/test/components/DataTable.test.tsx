import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import DataTable, { type ColumnDef } from "../../src/components/common/DataTable";

interface TestRow {
  id: number;
  name: string;
  status: string;
}

const columns: ColumnDef<TestRow>[] = [
  { key: "id", header: "ID", sortable: true },
  { key: "name", header: "Name", sortable: true },
  {
    key: "status",
    header: "Status",
    render: (row) => <span data-testid={`status-${row.id}`}>{row.status.toUpperCase()}</span>,
  },
];

const sampleData: TestRow[] = [
  { id: 1, name: "Alice", status: "active" },
  { id: 2, name: "Bob", status: "inactive" },
];

describe("DataTable", () => {
  it("renders column headers", () => {
    render(<DataTable columns={columns} data={sampleData} />);
    expect(screen.getByText("ID")).toBeInTheDocument();
    expect(screen.getByText("Name")).toBeInTheDocument();
    expect(screen.getByText("Status")).toBeInTheDocument();
  });

  it("renders data rows", () => {
    render(<DataTable columns={columns} data={sampleData} />);
    expect(screen.getByText("Alice")).toBeInTheDocument();
    expect(screen.getByText("Bob")).toBeInTheDocument();
  });

  it("uses custom render function", () => {
    render(<DataTable columns={columns} data={sampleData} />);
    expect(screen.getByTestId("status-1")).toHaveTextContent("ACTIVE");
  });

  it("renders EmptyState when data is empty", () => {
    render(<DataTable columns={columns} data={[]} emptyMessage="No records" />);
    expect(screen.getByText("No records")).toBeInTheDocument();
  });

  it("renders loading spinner when loading and no data", () => {
    render(<DataTable columns={columns} data={[]} loading />);
    expect(screen.getByText("Loading data...")).toBeInTheDocument();
  });

  it("renders skeleton rows when loading with existing data", () => {
    render(<DataTable columns={columns} data={sampleData} loading />);
    // Should still show data but with skeleton overlay indicators
    const skeletons = document.querySelectorAll(".MuiSkeleton-root");
    expect(skeletons.length).toBeGreaterThan(0);
  });

  it("calls onRowClick when a row is clicked", () => {
    const onRowClick = vi.fn();
    render(
      <DataTable columns={columns} data={sampleData} onRowClick={onRowClick} />
    );
    fireEvent.click(screen.getByText("Alice"));
    expect(onRowClick).toHaveBeenCalledWith(sampleData[0]);
  });

  it("shows sortable column headers and triggers onSort", () => {
    const onSort = vi.fn();
    render(
      <DataTable columns={columns} data={sampleData} onSort={onSort} />
    );
    const idHeader = screen.getByText("ID");
    fireEvent.click(idHeader);
    expect(onSort).toHaveBeenCalledWith({ field: "id", direction: "asc" });
  });

  it("toggles sort direction", () => {
    const onSort = vi.fn();
    render(
      <DataTable
        columns={columns}
        data={sampleData}
        onSort={onSort}
        sort={{ field: "id", direction: "asc" }}
      />
    );
    fireEvent.click(screen.getByText("ID"));
    expect(onSort).toHaveBeenCalledWith({ field: "id", direction: "desc" });
  });

  it("renders pagination when provided", () => {
    const onPageChange = vi.fn();
    render(
      <DataTable
        columns={columns}
        data={sampleData}
        pagination={{ page: 0, limit: 10, total: 25 }}
        onPageChange={onPageChange}
      />
    );
    expect(screen.getByText("1–10 of 25")).toBeInTheDocument();
  });

  it("uses getRowId for row keys", () => {
    const getRowId = vi.fn((row: TestRow) => `row-${row.id}`);
    render(
      <DataTable columns={columns} data={sampleData} getRowId={getRowId} />
    );
    expect(getRowId).toHaveBeenCalled();
  });

  it("handles missing pagination gracefully", () => {
    render(<DataTable columns={columns} data={sampleData} />);
    // Should not show pagination controls
    expect(screen.queryByRole("navigation")).not.toBeInTheDocument();
  });
});
