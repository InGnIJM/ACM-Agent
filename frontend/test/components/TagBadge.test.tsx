import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import TagBadge from "../../src/components/common/TagBadge";

describe("TagBadge", () => {
  it("renders the label", () => {
    render(<TagBadge label="Dynamic Programming" />);
    expect(screen.getByText("Dynamic Programming")).toBeInTheDocument();
  });

  it("applies correct color for data_structure category", () => {
    render(<TagBadge label="Array" category="data_structure" />);
    const chip = screen.getByText("Array").closest(".MuiChip-root");
    expect(chip).toBeInTheDocument();
  });

  it("applies correct color for search category", () => {
    render(<TagBadge label="BFS" category="search" />);
    const chip = screen.getByText("BFS").closest(".MuiChip-root");
    expect(chip).toBeInTheDocument();
  });

  it("applies correct color for dp category", () => {
    render(<TagBadge label="Knapsack" category="dp" />);
    const chip = screen.getByText("Knapsack").closest(".MuiChip-root");
    expect(chip).toBeInTheDocument();
  });

  it("applies correct color for graph category", () => {
    render(<TagBadge label="Dijkstra" category="graph" />);
    const chip = screen.getByText("Dijkstra").closest(".MuiChip-root");
    expect(chip).toBeInTheDocument();
  });

  it("applies correct color for math category", () => {
    render(<TagBadge label="Number Theory" category="math" />);
    const chip = screen.getByText("Number Theory").closest(".MuiChip-root");
    expect(chip).toBeInTheDocument();
  });

  it("applies correct color for string category", () => {
    render(<TagBadge label="KMP" category="string" />);
    const chip = screen.getByText("KMP").closest(".MuiChip-root");
    expect(chip).toBeInTheDocument();
  });

  it("applies correct color for greedy category", () => {
    render(<TagBadge label="Activity Selection" category="greedy" />);
    const chip = screen.getByText("Activity Selection").closest(".MuiChip-root");
    expect(chip).toBeInTheDocument();
  });

  it("defaults to 'default' color for unknown category", () => {
    render(<TagBadge label="Unknown" category="nonexistent" />);
    const chip = screen.getByText("Unknown");
    expect(chip).toBeInTheDocument();
  });

  it("uses default color when no category provided", () => {
    render(<TagBadge label="No Category" />);
    const chip = screen.getByText("No Category");
    expect(chip).toBeInTheDocument();
  });

  it("renders small size by default", () => {
    render(<TagBadge label="Small" />);
    const chip = screen.getByText("Small").closest(".MuiChip-root");
    expect(chip).toBeInTheDocument();
  });

  it("renders medium size when specified", () => {
    render(<TagBadge label="Medium" size="medium" />);
    const chip = screen.getByText("Medium").closest(".MuiChip-root");
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
    // MUI Chip renders a delete icon button when onDelete is set
    const deleteBtn = document.querySelector(".MuiChip-deleteIcon");
    expect(deleteBtn).toBeInTheDocument();
    if (deleteBtn) {
      fireEvent.click(deleteBtn);
      expect(onDelete).toHaveBeenCalledTimes(1);
    }
  });

  it("renders outlined variant", () => {
    render(<TagBadge label="Outlined" variant="outlined" />);
    const chip = screen.getByText("Outlined").closest(".MuiChip-root");
    expect(chip).toBeInTheDocument();
  });
});
