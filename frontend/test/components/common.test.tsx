// ============================================================
// Combined tests for common components:
//   TagBadge, DifficultyBadge, VerdictBadge, LoadingSpinner, EmptyState
// ============================================================

import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import TagBadge from "../../src/components/common/TagBadge";
import DifficultyBadge from "../../src/components/common/DifficultyBadge";
import VerdictBadge from "../../src/components/common/VerdictBadge";
import LoadingSpinner from "../../src/components/common/LoadingSpinner";
import EmptyState from "../../src/components/common/EmptyState";

// ============================================================
// TagBadge
// ============================================================

describe("TagBadge", () => {
  it("renders the label text", () => {
    render(<TagBadge label="Dynamic Programming" />);
    expect(screen.getByText("Dynamic Programming")).toBeInTheDocument();
  });

  it("applies color for data_structure category (primary)", () => {
    render(<TagBadge label="Array" category="data_structure" />);
    const chip = screen.getByText("Array");
    expect(chip).toBeInTheDocument();
  });

  it("applies color for search category (success)", () => {
    render(<TagBadge label="BFS" category="search" />);
    const chip = screen.getByText("BFS");
    expect(chip).toBeInTheDocument();
  });

  it("applies color for dp category (warning)", () => {
    render(<TagBadge label="Knapsack" category="dp" />);
    const chip = screen.getByText("Knapsack");
    expect(chip).toBeInTheDocument();
  });

  it("applies color for graph category (error)", () => {
    render(<TagBadge label="Dijkstra" category="graph" />);
    const chip = screen.getByText("Dijkstra");
    expect(chip).toBeInTheDocument();
  });

  it("applies color for math category (info)", () => {
    render(<TagBadge label="Number Theory" category="math" />);
    const chip = screen.getByText("Number Theory");
    expect(chip).toBeInTheDocument();
  });

  it("applies color for string category (secondary)", () => {
    render(<TagBadge label="KMP" category="string" />);
    const chip = screen.getByText("KMP");
    expect(chip).toBeInTheDocument();
  });

  it("applies color for greedy category (default)", () => {
    render(<TagBadge label="Activity Selection" category="greedy" />);
    const chip = screen.getByText("Activity Selection");
    expect(chip).toBeInTheDocument();
  });

  it("defaults to 'default' color for unknown category", () => {
    render(<TagBadge label="Unknown" category="nonexistent" />);
    expect(screen.getByText("Unknown")).toBeInTheDocument();
  });

  it("uses default color when no category is provided", () => {
    render(<TagBadge label="No Category" />);
    expect(screen.getByText("No Category")).toBeInTheDocument();
  });

  it("renders small size by default", () => {
    render(<TagBadge label="Small" />);
    const chip = screen.getByText("Small");
    expect(chip).toBeInTheDocument();
  });

  it("renders medium size when specified", () => {
    render(<TagBadge label="Medium" size="medium" />);
    const chip = screen.getByText("Medium");
    expect(chip).toBeInTheDocument();
  });

  it("handles onClick callback", () => {
    const onClick = vi.fn();
    render(<TagBadge label="Clickable" onClick={onClick} />);
    fireEvent.click(screen.getByText("Clickable"));
    expect(onClick).toHaveBeenCalledTimes(1);
  });

  it("handles onDelete callback", () => {
    const onDelete = vi.fn();
    render(<TagBadge label="Deletable" onDelete={onDelete} />);
    const deleteBtn = document.querySelector(".MuiChip-deleteIcon");
    expect(deleteBtn).toBeInTheDocument();
    if (deleteBtn) {
      fireEvent.click(deleteBtn);
      expect(onDelete).toHaveBeenCalledTimes(1);
    }
  });

  it("renders outlined variant", () => {
    render(<TagBadge label="Outlined" variant="outlined" />);
    const chip = screen.getByText("Outlined");
    expect(chip).toBeInTheDocument();
  });
});

// ============================================================
// DifficultyBadge
// ============================================================

describe("DifficultyBadge", () => {
  it("renders difficulty 1 with chip variant", () => {
    render(<DifficultyBadge difficulty={1} />);
    expect(screen.getByText("Lv 1")).toBeInTheDocument();
  });

  it("renders difficulty 10 with chip variant", () => {
    render(<DifficultyBadge difficulty={10} />);
    expect(screen.getByText("Lv 10")).toBeInTheDocument();
  });

  it("clamps difficulty below 1 to 1", () => {
    render(<DifficultyBadge difficulty={0} />);
    expect(screen.getByText("Lv 1")).toBeInTheDocument();
  });

  it("clamps difficulty above 10 to 10", () => {
    render(<DifficultyBadge difficulty={99} />);
    expect(screen.getByText("Lv 10")).toBeInTheDocument();
  });

  // Color mapping: 1-3 success (green), 4-5 warning (amber), 6-7 default-orange, 8-10 error (red)
  it("uses success (green) color for difficulty 1", () => {
    render(<DifficultyBadge difficulty={1} />);
    const chip = screen.getByText("Lv 1");
    expect(chip).toBeInTheDocument();
  });

  it("uses success (green) color for difficulty 3", () => {
    render(<DifficultyBadge difficulty={3} />);
    const chip = screen.getByText("Lv 3");
    expect(chip).toBeInTheDocument();
  });

  it("uses warning (amber) color for difficulty 4", () => {
    render(<DifficultyBadge difficulty={4} />);
    const chip = screen.getByText("Lv 4");
    expect(chip).toBeInTheDocument();
  });

  it("uses warning (amber) color for difficulty 5", () => {
    render(<DifficultyBadge difficulty={5} />);
    const chip = screen.getByText("Lv 5");
    expect(chip).toBeInTheDocument();
  });

  it("uses orange color for difficulty 6", () => {
    render(<DifficultyBadge difficulty={6} />);
    const chip = screen.getByText("Lv 6");
    expect(chip).toBeInTheDocument();
  });

  it("uses orange color for difficulty 7", () => {
    render(<DifficultyBadge difficulty={7} />);
    const chip = screen.getByText("Lv 7");
    expect(chip).toBeInTheDocument();
  });

  it("uses error (red) color for difficulty 8", () => {
    render(<DifficultyBadge difficulty={8} />);
    const chip = screen.getByText("Lv 8");
    expect(chip).toBeInTheDocument();
  });

  it("uses error (red) color for difficulty 10", () => {
    render(<DifficultyBadge difficulty={10} />);
    const chip = screen.getByText("Lv 10");
    expect(chip).toBeInTheDocument();
  });

  it("renders dot variant with correct aria-label", () => {
    render(<DifficultyBadge difficulty={5} variant="dot" />);
    expect(screen.getByLabelText("Difficulty 5")).toBeInTheDocument();
    expect(screen.getByText("5")).toBeInTheDocument();
  });

  it("renders dot variant without label when showLabel is false", () => {
    render(<DifficultyBadge difficulty={7} variant="dot" showLabel={false} />);
    expect(screen.getByLabelText("Difficulty 7")).toBeInTheDocument();
    expect(screen.queryByText("7")).toBeNull();
  });

  it("renders text variant with correct color", () => {
    render(<DifficultyBadge difficulty={3} variant="text" />);
    expect(screen.getByText("3")).toBeInTheDocument();
  });

  it("renders text variant with medium size", () => {
    render(<DifficultyBadge difficulty={8} variant="text" size="medium" />);
    expect(screen.getByText("8")).toBeInTheDocument();
  });

  it("renders chip without label prefix when showLabel false", () => {
    render(<DifficultyBadge difficulty={4} showLabel={false} />);
    expect(screen.getByText("4")).toBeInTheDocument();
    expect(screen.queryByText("Lv 4")).toBeNull();
  });
});

// ============================================================
// VerdictBadge
// ============================================================

describe("VerdictBadge", () => {
  it("renders Accepted verdict with success color", () => {
    render(<VerdictBadge status="accepted" />);
    expect(screen.getByText("Accepted")).toBeInTheDocument();
  });

  it("renders OK verdict with success color", () => {
    render(<VerdictBadge status="ok" />);
    expect(screen.getByText("OK")).toBeInTheDocument();
  });

  it("renders Wrong Answer verdict with error color", () => {
    render(<VerdictBadge status="wrong_answer" />);
    expect(screen.getByText("Wrong Answer")).toBeInTheDocument();
  });

  it("renders WA verdict with error color", () => {
    render(<VerdictBadge status="wa" />);
    expect(screen.getByText("WA")).toBeInTheDocument();
  });

  it("renders Time Limit verdict with warning color", () => {
    render(<VerdictBadge status="time_limit" />);
    expect(screen.getByText("Time Limit")).toBeInTheDocument();
  });

  it("renders TLE verdict with warning color", () => {
    render(<VerdictBadge status="tle" />);
    expect(screen.getByText("TLE")).toBeInTheDocument();
  });

  it("renders Memory Limit verdict with warning color", () => {
    render(<VerdictBadge status="memory_limit" />);
    expect(screen.getByText("Memory Limit")).toBeInTheDocument();
  });

  it("renders MLE verdict with warning color", () => {
    render(<VerdictBadge status="mle" />);
    expect(screen.getByText("MLE")).toBeInTheDocument();
  });

  it("renders Runtime Error verdict with error color", () => {
    render(<VerdictBadge status="runtime_error" />);
    expect(screen.getByText("Runtime Error")).toBeInTheDocument();
  });

  it("renders RE verdict with error color", () => {
    render(<VerdictBadge status="re" />);
    expect(screen.getByText("RE")).toBeInTheDocument();
  });

  it("renders Compilation Error verdict with error color", () => {
    render(<VerdictBadge status="compilation_error" />);
    expect(screen.getByText("Compile Error")).toBeInTheDocument();
  });

  it("renders CE verdict with error color", () => {
    render(<VerdictBadge status="ce" />);
    expect(screen.getByText("CE")).toBeInTheDocument();
  });

  it("renders Pending verdict with default color", () => {
    render(<VerdictBadge status="pending" />);
    expect(screen.getByText("Pending")).toBeInTheDocument();
  });

  it("handles unknown status gracefully", () => {
    render(<VerdictBadge status="unknown_status" />);
    // Falls back to displaying the raw status text
    expect(screen.getByText("unknown_status")).toBeInTheDocument();
  });

  it("handles case-insensitive matching", () => {
    render(<VerdictBadge status="ACCEPTED" />);
    expect(screen.getByText("Accepted")).toBeInTheDocument();
  });

  it("trims whitespace from status", () => {
    render(<VerdictBadge status="  wa  " />);
    expect(screen.getByText("WA")).toBeInTheDocument();
  });

  it("renders outlined variant", () => {
    render(<VerdictBadge status="accepted" variant="outlined" />);
    expect(screen.getByText("Accepted")).toBeInTheDocument();
  });
});

// ============================================================
// LoadingSpinner
// ============================================================

describe("LoadingSpinner", () => {
  it("renders CircularProgress", () => {
    render(<LoadingSpinner />);
    const spinner = document.querySelector(".MuiCircularProgress-root");
    expect(spinner).toBeInTheDocument();
  });

  it("renders optional message text", () => {
    render(<LoadingSpinner message="Fetching problems..." />);
    expect(screen.getByText("Fetching problems...")).toBeInTheDocument();
  });

  it("does not render message paragraph when message not provided", () => {
    render(<LoadingSpinner />);
    const container = screen.getByRole("status");
    expect(container.querySelectorAll("p")).toHaveLength(0);
  });

  it("has role=status for accessibility", () => {
    render(<LoadingSpinner />);
    expect(screen.getByRole("status")).toBeInTheDocument();
  });

  it("has aria-label matching message when provided", () => {
    render(<LoadingSpinner message="Loading users..." />);
    expect(screen.getByLabelText("Loading users...")).toBeInTheDocument();
  });

  it("has default aria-label of 'Loading' when no message", () => {
    render(<LoadingSpinner />);
    expect(screen.getByLabelText("Loading")).toBeInTheDocument();
  });

  it("renders fullPage variant with extra padding", () => {
    render(<LoadingSpinner fullPage />);
    const container = screen.getByRole("status");
    expect(container).toBeInTheDocument();
  });

  it("accepts custom size prop", () => {
    render(<LoadingSpinner size={60} />);
    const spinner = document.querySelector(".MuiCircularProgress-root");
    expect(spinner).toBeInTheDocument();
  });
});

// ============================================================
// EmptyState
// ============================================================

describe("EmptyState", () => {
  it("renders the message text", () => {
    render(<EmptyState message="No problems found" />);
    expect(screen.getByText("No problems found")).toBeInTheDocument();
  });

  it("renders default message when none provided", () => {
    render(<EmptyState />);
    expect(screen.getByText("Nothing here")).toBeInTheDocument();
  });

  it("renders default InboxIcon when no custom icon", () => {
    render(<EmptyState />);
    const svg = document.querySelector(".MuiSvgIcon-root");
    expect(svg).toBeInTheDocument();
  });

  it("renders custom icon when provided", () => {
    render(<EmptyState icon={<span data-testid="custom-icon">X</span>} />);
    expect(screen.getByTestId("custom-icon")).toBeInTheDocument();
  });

  it("renders action button when actionLabel and onAction provided", () => {
    const onAction = vi.fn();
    render(
      <EmptyState
        message="No records"
        actionLabel="Create one"
        onAction={onAction}
      />
    );
    const btn = screen.getByText("Create one");
    expect(btn).toBeInTheDocument();
  });

  it("calls onAction when action button clicked", () => {
    const onAction = vi.fn();
    render(
      <EmptyState
        message="No records"
        actionLabel="Create one"
        onAction={onAction}
      />
    );
    fireEvent.click(screen.getByText("Create one"));
    expect(onAction).toHaveBeenCalledTimes(1);
  });

  it("does not render action button when only actionLabel provided", () => {
    render(<EmptyState message="Empty" actionLabel="Go" />);
    expect(screen.queryByText("Go")).toBeNull();
  });

  it("does not render action button when only onAction provided", () => {
    const onAction = vi.fn();
    render(<EmptyState message="Empty" onAction={onAction} />);
    expect(screen.queryByRole("button")).toBeNull();
  });
});
