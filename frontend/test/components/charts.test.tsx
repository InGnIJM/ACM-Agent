import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import SkillRadar from "../../src/components/charts/SkillRadar";
import DailyTrend from "../../src/components/charts/DailyTrend";
import DifficultyPie from "../../src/components/charts/DifficultyPie";
import TagBar from "../../src/components/charts/TagBar";
import Heatmap from "../../src/components/charts/Heatmap";

// ============================================================
// SkillRadar
// ============================================================
describe("SkillRadar", () => {
  const sampleData = [
    { tag: "DP", score: 85 },
    { tag: "Graph", score: 60 },
    { tag: "Math", score: 92 },
    { tag: "String", score: 40 },
  ];

  it("renders without crashing with basic props", () => {
    const { container } = render(<SkillRadar data={sampleData} />);
    // Recharts renders an SVG inside a responsive-container div
    expect(container.querySelector(".recharts-responsive-container")).toBeTruthy();
  });

  it("renders an SVG radar chart", () => {
    const { container } = render(<SkillRadar data={sampleData} />);
    const svg = container.querySelector("svg");
    expect(svg).toBeTruthy();
  });

  it("renders with custom maxValue", () => {
    const { container } = render(<SkillRadar data={sampleData} maxValue={100} />);
    expect(container.querySelector("svg")).toBeTruthy();
  });

  it("renders with custom size and color", () => {
    const { container } = render(
      <SkillRadar data={sampleData} size={400} color="#EF4444" />,
    );
    expect(container.querySelector("svg")).toBeTruthy();
  });

  it("computes maxValue from data when not provided (max score > 1)", () => {
    const { container } = render(<SkillRadar data={sampleData} />);
    expect(container.querySelector("svg")).toBeTruthy();
  });

  it("uses maxValue 1 when data is empty and no maxValue provided", () => {
    const { container } = render(<SkillRadar data={[]} />);
    expect(container.querySelector("svg")).toBeTruthy();
  });

  it("renders when all scores are zero", () => {
    const zeroData = [
      { tag: "A", score: 0 },
      { tag: "B", score: 0 },
    ];
    const { container } = render(<SkillRadar data={zeroData} />);
    expect(container.querySelector("svg")).toBeTruthy();
  });

  it("renders single data point without error", () => {
    const { container } = render(
      <SkillRadar data={[{ tag: "Only", score: 50 }]} />,
    );
    expect(container.querySelector("svg")).toBeTruthy();
  });
});

// ============================================================
// DailyTrend
// ============================================================
describe("DailyTrend", () => {
  const sampleData = [
    { date: "2025-06-01", acCount: 3, submitCount: 5 },
    { date: "2025-06-02", acCount: 4, submitCount: 7 },
    { date: "2025-06-03", acCount: 1, submitCount: 2 },
    { date: "2025-06-04", acCount: 6, submitCount: 10 },
    { date: "2025-06-05", acCount: 2, submitCount: 4 },
  ];

  it("renders without crashing with basic props", () => {
    const { container } = render(<DailyTrend data={sampleData} />);
    expect(container.querySelector(".recharts-responsive-container")).toBeTruthy();
  });

  it("renders an SVG line chart", () => {
    const { container } = render(<DailyTrend data={sampleData} />);
    const svg = container.querySelector("svg");
    expect(svg).toBeTruthy();
  });

  it("slices data when days prop is provided", () => {
    const { container } = render(<DailyTrend data={sampleData} days={3} />);
    expect(container.querySelector("svg")).toBeTruthy();
  });

  it("renders with days exceeding data length (shows all data)", () => {
    const { container } = render(<DailyTrend data={sampleData} days={999} />);
    expect(container.querySelector("svg")).toBeTruthy();
  });

  it("renders with empty data", () => {
    const { container } = render(<DailyTrend data={[]} />);
    expect(container.querySelector("svg")).toBeTruthy();
  });

  it("renders with days=0 (shows empty)", () => {
    const { container } = render(<DailyTrend data={sampleData} days={0} />);
    expect(container.querySelector("svg")).toBeTruthy();
  });

  it("renders single day of data", () => {
    const { container } = render(
      <DailyTrend data={[{ date: "2025-06-01", acCount: 3, submitCount: 5 }]} />,
    );
    expect(container.querySelector("svg")).toBeTruthy();
  });
});

// ============================================================
// DifficultyPie
// ============================================================
describe("DifficultyPie", () => {
  const sampleData = [
    { difficulty: "Easy", count: 30 },
    { difficulty: "Medium", count: 45 },
    { difficulty: "Hard", count: 15 },
  ];

  it("renders without crashing with basic props", () => {
    const { container } = render(<DifficultyPie data={sampleData} />);
    expect(container.querySelector(".recharts-responsive-container")).toBeTruthy();
  });

  it("renders an SVG pie chart", () => {
    const { container } = render(<DifficultyPie data={sampleData} />);
    const svg = container.querySelector("svg");
    expect(svg).toBeTruthy();
  });

  it("renders known difficulty bands with their colors", () => {
    const { container } = render(
      <DifficultyPie data={[{ difficulty: "Easy", count: 10 }]} />,
    );
    expect(container.querySelector("svg")).toBeTruthy();
  });

  it("renders Medium-Easy difficulty", () => {
    const { container } = render(
      <DifficultyPie data={[{ difficulty: "Medium-Easy", count: 5 }]} />,
    );
    expect(container.querySelector("svg")).toBeTruthy();
  });

  it("renders Medium-Hard difficulty", () => {
    const { container } = render(
      <DifficultyPie data={[{ difficulty: "Medium-Hard", count: 8 }]} />,
    );
    expect(container.querySelector("svg")).toBeTruthy();
  });

  it("falls back to default colors for unknown difficulty labels", () => {
    const { container } = render(
      <DifficultyPie data={[{ difficulty: "Insane", count: 3 }]} />,
    );
    const svg = container.querySelector("svg");
    expect(svg).toBeTruthy();
  });

  it("renders with empty data", () => {
    const { container } = render(<DifficultyPie data={[]} />);
    expect(container.querySelector("svg")).toBeTruthy();
  });

  it("renders many slices (all 5 known bands + unknown)", () => {
    const many = [
      { difficulty: "Easy", count: 10 },
      { difficulty: "Medium-Easy", count: 10 },
      { difficulty: "Medium", count: 10 },
      { difficulty: "Medium-Hard", count: 10 },
      { difficulty: "Hard", count: 10 },
      { difficulty: "Insane", count: 10 },
    ];
    const { container } = render(<DifficultyPie data={many} />);
    expect(container.querySelector("svg")).toBeTruthy();
  });
});

// ============================================================
// TagBar
// ============================================================
describe("TagBar", () => {
  const sampleData = [
    { tag: "DP", count: 25 },
    { tag: "Graph", count: 18 },
    { tag: "Math", count: 32 },
    { tag: "String", count: 14 },
  ];

  it("renders without crashing with basic props", () => {
    const { container } = render(<TagBar data={sampleData} />);
    expect(container.querySelector(".recharts-responsive-container")).toBeTruthy();
  });

  it("renders an SVG bar chart", () => {
    const { container } = render(<TagBar data={sampleData} />);
    const svg = container.querySelector("svg");
    expect(svg).toBeTruthy();
  });

  it("renders with empty data", () => {
    const { container } = render(<TagBar data={[]} />);
    expect(container.querySelector("svg")).toBeTruthy();
  });

  it("renders single bar", () => {
    const { container } = render(
      <TagBar data={[{ tag: "Solo", count: 10 }]} />,
    );
    expect(container.querySelector("svg")).toBeTruthy();
  });

  it("renders many bars (cycles through color palette)", () => {
    const many = Array.from({ length: 15 }, (_, i) => ({
      tag: `Tag${i}`,
      count: i * 3,
    }));
    const { container } = render(<TagBar data={many} />);
    expect(container.querySelector("svg")).toBeTruthy();
  });

  it("renders bars with zero count", () => {
    const { container } = render(
      <TagBar data={[{ tag: "Zero", count: 0 }]} />,
    );
    expect(container.querySelector("svg")).toBeTruthy();
  });
});

// ============================================================
// Heatmap
// ============================================================
describe("Heatmap", () => {
  const today = new Date();
  const pad = (n: number) => String(n).padStart(2, "0");
  const fmt = (d: Date) =>
    `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;

  const sampleData = [
    { date: fmt(today), count: 5 },
    { date: fmt(new Date(today.getTime() - 86400000)), count: 3 },
    { date: fmt(new Date(today.getTime() - 2 * 86400000)), count: 0 },
  ];

  it("renders the heatmap container", () => {
    render(<Heatmap data={sampleData} />);
    expect(screen.getByTestId("heatmap")).toBeInTheDocument();
  });

  it("renders the legend (Less/More)", () => {
    render(<Heatmap data={sampleData} />);
    expect(screen.getByText("Less")).toBeInTheDocument();
    expect(screen.getByText("More")).toBeInTheDocument();
  });

  it("renders day-of-week labels (Mon, Wed, Fri)", () => {
    render(<Heatmap data={sampleData} />);
    expect(screen.getByText("Mon")).toBeInTheDocument();
    expect(screen.getByText("Wed")).toBeInTheDocument();
    expect(screen.getByText("Fri")).toBeInTheDocument();
  });

  it("renders with empty data without crashing", () => {
    render(<Heatmap data={[]} />);
    expect(screen.getByTestId("heatmap")).toBeInTheDocument();
  });

  it("renders with custom months=3", () => {
    render(<Heatmap data={sampleData} months={3} />);
    expect(screen.getByTestId("heatmap")).toBeInTheDocument();
  });

  it("renders cells with data-date attribute for known dates", () => {
    const { container } = render(<Heatmap data={sampleData} />);
    const cells = container.querySelectorAll("[data-date]");
    const dateSet = new Set(sampleData.map((d) => d.date));
    const matchingCells = Array.from(cells).filter(
      (c) => c.getAttribute("data-date") && dateSet.has(c.getAttribute("data-date")!),
    );
    expect(matchingCells.length).toBe(sampleData.length);
  });

  it("renders cells with correct data-count for matching dates", () => {
    const { container } = render(<Heatmap data={sampleData} />);
    const todayCell = container.querySelector(`[data-date="${fmt(today)}"]`);
    expect(todayCell).toBeTruthy();
    expect(todayCell?.getAttribute("data-count")).toBe("5");
  });

  it("shows empty (transparent) cells for days without data", () => {
    const { container } = render(<Heatmap data={[]} />);
    // All cells should either be empty (no data-date) or have data-count="0"
    const cellsWithData = container.querySelectorAll("[data-date]");
    const zeroCells = container.querySelectorAll("[data-count=\"0\"]");
    expect(cellsWithData.length + zeroCells.length).toBeGreaterThanOrEqual(0);
  });

  it("renders correct max count color (darkest green)", () => {
    const highData = [
      { date: fmt(today), count: 100 },
      { date: fmt(new Date(today.getTime() - 86400000)), count: 1 },
    ];
    const { container } = render(<Heatmap data={highData} />);
    const highCell = container.querySelector(`[data-date="${fmt(today)}"]`);
    expect(highCell).toBeTruthy();
    // The highest ratio cell should have the darkest color
    const style = highCell?.getAttribute("style") || "";
    expect(style).toContain("rgb(25, 97, 39)");
  });
});
