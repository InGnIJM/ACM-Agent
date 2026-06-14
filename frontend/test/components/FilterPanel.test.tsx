import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import FilterPanel from "../../src/components/common/FilterPanel";
import type { FilterPanelOption } from "../../src/components/common/FilterPanel";

const platforms: FilterPanelOption[] = [
  { value: "codeforces", label: "Codeforces" },
  { value: "leetcode", label: "LeetCode" },
  { value: "atcoder", label: "AtCoder" },
];

const tags: FilterPanelOption[] = [
  { value: "dp", label: "Dynamic Programming" },
  { value: "graph", label: "Graph Theory" },
  { value: "math", label: "Mathematics" },
];

describe("FilterPanel", () => {
  it("renders collapsed by default", () => {
    render(
      <FilterPanel
        platforms={platforms}
        selectedPlatforms={[]}
        onPlatformsChange={vi.fn()}
        difficultyRange={[1, 10]}
        onDifficultyRangeChange={vi.fn()}
        tags={tags}
        selectedTags={[]}
        onTagsChange={vi.fn()}
      />
    );
    // The accordion trigger should have aria-expanded="false" when collapsed
    const trigger = screen.getByRole("button", { name: /filters/i });
    expect(trigger).toHaveAttribute("aria-expanded", "false");
  });

  it("expands when clicked", () => {
    render(
      <FilterPanel
        platforms={platforms}
        selectedPlatforms={[]}
        onPlatformsChange={vi.fn()}
        difficultyRange={[1, 10]}
        onDifficultyRangeChange={vi.fn()}
        tags={tags}
        selectedTags={[]}
        onTagsChange={vi.fn()}
      />
    );
    fireEvent.click(screen.getByText("Filters"));
    expect(screen.getByText("Platform")).toBeInTheDocument();
  });

  it("renders expanded when defaultExpanded is true", () => {
    render(
      <FilterPanel
        platforms={platforms}
        selectedPlatforms={[]}
        onPlatformsChange={vi.fn()}
        difficultyRange={[1, 10]}
        onDifficultyRangeChange={vi.fn()}
        tags={tags}
        selectedTags={[]}
        onTagsChange={vi.fn()}
        defaultExpanded
      />
    );
    expect(screen.getByText("Platform")).toBeInTheDocument();
  });

  it("renders platform checkboxes", () => {
    render(
      <FilterPanel
        platforms={platforms}
        selectedPlatforms={[]}
        onPlatformsChange={vi.fn()}
        difficultyRange={[1, 10]}
        onDifficultyRangeChange={vi.fn()}
        tags={tags}
        selectedTags={[]}
        onTagsChange={vi.fn()}
        defaultExpanded
      />
    );
    expect(screen.getByText("Codeforces")).toBeInTheDocument();
    expect(screen.getByText("LeetCode")).toBeInTheDocument();
    expect(screen.getByText("AtCoder")).toBeInTheDocument();
  });

  it("toggles platform selection on click", () => {
    const onPlatformsChange = vi.fn();
    render(
      <FilterPanel
        platforms={platforms}
        selectedPlatforms={[]}
        onPlatformsChange={onPlatformsChange}
        difficultyRange={[1, 10]}
        onDifficultyRangeChange={vi.fn()}
        tags={tags}
        selectedTags={[]}
        onTagsChange={vi.fn()}
        defaultExpanded
      />
    );
    fireEvent.click(screen.getByText("Codeforces"));
    expect(onPlatformsChange).toHaveBeenCalledWith(["codeforces"]);
  });

  it("removes platform when already selected", () => {
    const onPlatformsChange = vi.fn();
    render(
      <FilterPanel
        platforms={platforms}
        selectedPlatforms={["codeforces"]}
        onPlatformsChange={onPlatformsChange}
        difficultyRange={[1, 10]}
        onDifficultyRangeChange={vi.fn()}
        tags={tags}
        selectedTags={[]}
        onTagsChange={vi.fn()}
        defaultExpanded
      />
    );
    fireEvent.click(screen.getByText("Codeforces"));
    expect(onPlatformsChange).toHaveBeenCalledWith([]);
  });

  it("renders difficulty range slider", () => {
    render(
      <FilterPanel
        platforms={platforms}
        selectedPlatforms={[]}
        onPlatformsChange={vi.fn()}
        difficultyRange={[3, 7]}
        onDifficultyRangeChange={vi.fn()}
        tags={tags}
        selectedTags={[]}
        onTagsChange={vi.fn()}
        defaultExpanded
      />
    );
    expect(screen.getByText("Difficulty: 3 - 7")).toBeInTheDocument();
  });

  it("renders tag autocomplete", () => {
    render(
      <FilterPanel
        platforms={platforms}
        selectedPlatforms={[]}
        onPlatformsChange={vi.fn()}
        difficultyRange={[1, 10]}
        onDifficultyRangeChange={vi.fn()}
        tags={tags}
        selectedTags={[]}
        onTagsChange={vi.fn()}
        defaultExpanded
      />
    );
    expect(screen.getByPlaceholderText("Select tags...")).toBeInTheDocument();
  });

  it("renders reset button when onReset provided", () => {
    render(
      <FilterPanel
        platforms={platforms}
        selectedPlatforms={[]}
        onPlatformsChange={vi.fn()}
        difficultyRange={[1, 10]}
        onDifficultyRangeChange={vi.fn()}
        tags={tags}
        selectedTags={[]}
        onTagsChange={vi.fn()}
        onReset={vi.fn()}
        defaultExpanded
      />
    );
    expect(screen.getByText("Reset Filters")).toBeInTheDocument();
  });

  it("reset button is disabled when no active filters", () => {
    render(
      <FilterPanel
        platforms={platforms}
        selectedPlatforms={[]}
        onPlatformsChange={vi.fn()}
        difficultyRange={[1, 10]}
        onDifficultyRangeChange={vi.fn()}
        tags={tags}
        selectedTags={[]}
        onTagsChange={vi.fn()}
        onReset={vi.fn()}
        defaultExpanded
      />
    );
    expect(screen.getByText("Reset Filters")).toBeDisabled();
  });

  it("reset button is enabled when filters are active", () => {
    render(
      <FilterPanel
        platforms={platforms}
        selectedPlatforms={["codeforces"]}
        onPlatformsChange={vi.fn()}
        difficultyRange={[1, 10]}
        onDifficultyRangeChange={vi.fn()}
        tags={tags}
        selectedTags={[]}
        onTagsChange={vi.fn()}
        onReset={vi.fn()}
        defaultExpanded
      />
    );
    expect(screen.getByText("Reset Filters")).not.toBeDisabled();
  });

  it("calls onReset when reset button clicked", () => {
    const onReset = vi.fn();
    render(
      <FilterPanel
        platforms={platforms}
        selectedPlatforms={["codeforces"]}
        onPlatformsChange={vi.fn()}
        difficultyRange={[1, 10]}
        onDifficultyRangeChange={vi.fn()}
        tags={tags}
        selectedTags={[]}
        onTagsChange={vi.fn()}
        onReset={onReset}
        defaultExpanded
      />
    );
    fireEvent.click(screen.getByText("Reset Filters"));
    expect(onReset).toHaveBeenCalledTimes(1);
  });

  it("shows active filter count chip", () => {
    render(
      <FilterPanel
        platforms={platforms}
        selectedPlatforms={["codeforces", "leetcode"]}
        onPlatformsChange={vi.fn()}
        difficultyRange={[3, 8]}
        onDifficultyRangeChange={vi.fn()}
        tags={tags}
        selectedTags={["dp"]}
        onTagsChange={vi.fn()}
        defaultExpanded
      />
    );
    // 2 platforms + 1 tag + 1 difficulty = 4
    expect(screen.getByText("4")).toBeInTheDocument();
  });

  it("does not show count chip when no active filters", () => {
    render(
      <FilterPanel
        platforms={platforms}
        selectedPlatforms={[]}
        onPlatformsChange={vi.fn()}
        difficultyRange={[1, 10]}
        onDifficultyRangeChange={vi.fn()}
        tags={tags}
        selectedTags={[]}
        onTagsChange={vi.fn()}
        defaultExpanded
      />
    );
    // The chip should not be rendered
    const chip = document.querySelector(".MuiChip-root");
    expect(chip).not.toBeInTheDocument();
  });
});
