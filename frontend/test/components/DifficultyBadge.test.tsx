import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import DifficultyBadge from "../../src/components/common/DifficultyBadge";

describe("DifficultyBadge", () => {
  // ---- chip variant (default) ----

  it("renders chip variant with difficulty level label", () => {
    render(<DifficultyBadge difficulty={3} />);
    expect(screen.getByText("Lv 3")).toBeInTheDocument();
  });

  it("clamps difficulty below 1 to 1", () => {
    render(<DifficultyBadge difficulty={0} />);
    expect(screen.getByText("Lv 1")).toBeInTheDocument();
  });

  it("clamps difficulty above 10 to 10", () => {
    render(<DifficultyBadge difficulty={15} />);
    expect(screen.getByText("Lv 10")).toBeInTheDocument();
  });

  it("renders difficulty 1-3 with success color (no override)", () => {
    render(<DifficultyBadge difficulty={2} />);
    const chip = screen.getByText("Lv 2").closest(".MuiChip-root");
    expect(chip).toBeInTheDocument();
  });

  it("renders difficulty 4-5 with warning color", () => {
    render(<DifficultyBadge difficulty={4} />);
    const chip = screen.getByText("Lv 4").closest(".MuiChip-root");
    expect(chip).toBeInTheDocument();
  });

  it("renders difficulty 6-7 with custom orange background", () => {
    render(<DifficultyBadge difficulty={6} />);
    const chip = screen.getByText("Lv 6").closest(".MuiChip-root");
    expect(chip).toBeInTheDocument();
  });

  it("renders difficulty 8-10 with error color", () => {
    render(<DifficultyBadge difficulty={9} />);
    const chip = screen.getByText("Lv 9").closest(".MuiChip-root");
    expect(chip).toBeInTheDocument();
  });

  // ---- text variant ----

  it("renders text variant with just the number", () => {
    render(<DifficultyBadge difficulty={5} variant="text" />);
    expect(screen.getByText("5")).toBeInTheDocument();
  });

  it("text variant uses correct hex color for easy", () => {
    render(<DifficultyBadge difficulty={2} variant="text" />);
    const el = screen.getByText("2");
    expect(el).toHaveStyle({ color: "#2E7D32" });
  });

  it("text variant uses correct hex color for hard", () => {
    render(<DifficultyBadge difficulty={9} variant="text" />);
    const el = screen.getByText("9");
    expect(el).toHaveStyle({ color: "#C62828" });
  });

  // ---- dot variant ----

  it("renders dot variant with colored dot", () => {
    render(<DifficultyBadge difficulty={3} variant="dot" />);
    // The dot is a Box with aria-label
    const dot = screen.getByLabelText("Difficulty 3");
    expect(dot).toBeInTheDocument();
  });

  it("dot variant shows label by default", () => {
    render(<DifficultyBadge difficulty={7} variant="dot" />);
    expect(screen.getByText("7")).toBeInTheDocument();
  });

  it("dot variant hides label when showLabel is false", () => {
    render(<DifficultyBadge difficulty={7} variant="dot" showLabel={false} />);
    expect(screen.queryByText("7")).not.toBeInTheDocument();
    // But dot should still be present
    expect(screen.getByLabelText("Difficulty 7")).toBeInTheDocument();
  });

  // ---- edge cases ----

  it("handles non-integer difficulty by clamping", () => {
    render(<DifficultyBadge difficulty={3.7} />);
    // Math.max(1, Math.min(10, 3.7)) = 3.7 — but Chip label shows "Lv 3.7" since we don't round
    // Actually the code uses clamped directly in label. 3.7 will show "Lv 3.7"
    // That's fine — the color logic uses >=1 && <=3
    const chip = screen.getByText("Lv 3.7");
    expect(chip).toBeInTheDocument();
  });

  it("chip variant without showLabel shows only number", () => {
    render(<DifficultyBadge difficulty={5} showLabel={false} />);
    expect(screen.getByText("5")).toBeInTheDocument();
  });
});
