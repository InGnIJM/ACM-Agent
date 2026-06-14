import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import SearchInput, { useDebounce } from "../../src/components/common/SearchInput";

// ============================================================
// useDebounce hook tests
// ============================================================

describe("useDebounce", () => {
  // We test the hook by rendering a small component that uses it
  it("returns initial value immediately", async () => {
    let result = "";
    function Tester({ value }: { value: string }) {
      const debounced = useDebounce(value, 300);
      result = debounced;
      return <span>{debounced}</span>;
    }

    render(<Tester value="hello" />);
    expect(screen.getByText("hello")).toBeInTheDocument();
    expect(result).toBe("hello");
  });

  // The debounce behavior is tested via SearchInput integration below
});

// ============================================================
// SearchInput tests
// ============================================================

describe("SearchInput", () => {
  it("renders with placeholder", () => {
    render(<SearchInput onSearch={vi.fn()} placeholder="Find problems..." />);
    expect(screen.getByPlaceholderText("Find problems...")).toBeInTheDocument();
  });

  it("renders default placeholder when not specified", () => {
    render(<SearchInput onSearch={vi.fn()} />);
    expect(screen.getByPlaceholderText("Search...")).toBeInTheDocument();
  });

  it("shows search icon", () => {
    render(<SearchInput onSearch={vi.fn()} />);
    const input = screen.getByPlaceholderText("Search...").closest(".MuiInputBase-root");
    expect(input?.querySelector("svg")).toBeTruthy();
  });

  it("fires onSearch with debounced value", async () => {
    const onSearch = vi.fn();
    render(<SearchInput onSearch={onSearch} debounceMs={100} />);

    const input = screen.getByPlaceholderText("Search...");
    fireEvent.change(input, { target: { value: "dp" } });

    // Wait for debounce
    await waitFor(() => {
      expect(onSearch).toHaveBeenCalledWith("dp");
    }, { timeout: 300 });
  });

  it("fires onSearch immediately when debounceMs is 0", () => {
    const onSearch = vi.fn();
    render(<SearchInput onSearch={onSearch} debounceMs={0} />);

    const input = screen.getByPlaceholderText("Search...");
    fireEvent.change(input, { target: { value: "graph" } });

    expect(onSearch).toHaveBeenCalledWith("graph");
  });

  it("shows clear button when value is present", () => {
    render(<SearchInput onSearch={vi.fn()} value="test" />);
    const clearBtn = screen.getByLabelText("Clear search");
    expect(clearBtn).toBeInTheDocument();
  });

  it("does not show clear button when value is empty", () => {
    render(<SearchInput onSearch={vi.fn()} value="" />);
    expect(screen.queryByLabelText("Clear search")).not.toBeInTheDocument();
  });

  it("clear button calls onSearch with empty string", () => {
    const onSearch = vi.fn();
    render(<SearchInput onSearch={onSearch} value="test" />);

    const clearBtn = screen.getByLabelText("Clear search");
    fireEvent.click(clearBtn);

    expect(onSearch).toHaveBeenCalledWith("");
  });

  it("does not show clear button when clearable is false", () => {
    render(<SearchInput onSearch={vi.fn()} value="test" clearable={false} />);
    expect(screen.queryByLabelText("Clear search")).not.toBeInTheDocument();
  });

  it("renders in disabled state", () => {
    render(<SearchInput onSearch={vi.fn()} disabled />);
    const input = screen.getByPlaceholderText("Search...");
    expect(input.closest("input")).toBeDisabled();
  });

  it("controlled mode: displays external value", () => {
    render(<SearchInput onSearch={vi.fn()} value="controlled" />);
    const input = screen.getByPlaceholderText("Search...") as HTMLInputElement;
    expect(input.value).toBe("controlled");
  });

  it("fullWidth by default", () => {
    render(<SearchInput onSearch={vi.fn()} />);
    const input = screen.getByPlaceholderText("Search...").closest(".MuiTextField-root");
    expect(input).toBeInTheDocument();
  });
});
