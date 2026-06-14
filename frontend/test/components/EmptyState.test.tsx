import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import EmptyState from "../../src/components/common/EmptyState";
import InboxIcon from "@mui/icons-material/Inbox";

describe("EmptyState", () => {
  it("renders default message", () => {
    render(<EmptyState />);
    expect(screen.getByText("Nothing here")).toBeInTheDocument();
  });

  it("renders custom message", () => {
    render(<EmptyState message="No problems found" />);
    expect(screen.getByText("No problems found")).toBeInTheDocument();
  });

  it("renders default inbox icon when no icon provided", () => {
    render(<EmptyState />);
    // Check that an SVG exists (InboxIcon renders SVG)
    const svg = document.querySelector("svg");
    expect(svg).toBeInTheDocument();
  });

  it("renders custom icon when provided", () => {
    render(<EmptyState icon={<InboxIcon data-testid="custom-icon" />} />);
    expect(screen.getByTestId("custom-icon")).toBeInTheDocument();
  });

  it("renders action button when actionLabel and onAction provided", () => {
    const onAction = vi.fn();
    render(
      <EmptyState
        message="No data"
        actionLabel="Refresh"
        onAction={onAction}
      />
    );
    const btn = screen.getByText("Refresh");
    expect(btn).toBeInTheDocument();
  });

  it("calls onAction when action button clicked", () => {
    const onAction = vi.fn();
    render(
      <EmptyState
        message="No data"
        actionLabel="Refresh"
        onAction={onAction}
      />
    );
    fireEvent.click(screen.getByText("Refresh"));
    expect(onAction).toHaveBeenCalledTimes(1);
  });

  it("does not render action button when only actionLabel provided", () => {
    render(<EmptyState message="No data" actionLabel="Refresh" />);
    expect(screen.queryByText("Refresh")).not.toBeInTheDocument();
  });

  it("does not render action button when only onAction provided", () => {
    render(<EmptyState message="No data" onAction={vi.fn()} />);
    // No button should appear since actionLabel is missing
    const buttons = document.querySelectorAll("button");
    expect(buttons).toHaveLength(0);
  });

  it("renders children when passed as message", () => {
    render(
      <EmptyState message={<span data-testid="custom-msg">Custom content</span>} />
    );
    expect(screen.getByTestId("custom-msg")).toBeInTheDocument();
  });
});
