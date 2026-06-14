import React, { useMemo } from "react";

export interface HeatmapDataPoint {
  date: string;
  count: number;
}

export interface HeatmapProps {
  data: HeatmapDataPoint[];
  months?: number;
}

const DAY_LABELS = ["", "Mon", "", "Wed", "", "Fri", ""];

const getColor = (count: number, maxCount: number): string => {
  if (count === 0) return "#EBEDF0";
  const ratio = maxCount > 0 ? count / maxCount : 0;
  if (ratio <= 0.25) return "#C6E48B";
  if (ratio <= 0.5) return "#7BC96F";
  if (ratio <= 0.75) return "#239A3B";
  return "#196127";
};

const getMonthLabel = (date: Date): string => {
  const months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  return months[date.getMonth()];
};

const formatDate = (d: Date): string => {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
};

const Heatmap: React.FC<HeatmapProps> = ({ data, months = 6 }) => {
  const { grid, monthLabels, maxCount } = useMemo(() => {
    const countMap = new Map<string, number>();
    for (const d of data) {
      countMap.set(d.date, d.count);
    }

    const today = new Date();
    today.setHours(0, 0, 0, 0);
    const totalDays = months * 31; // approximate
    const startDate = new Date(today);
    startDate.setDate(startDate.getDate() - totalDays);

    // Align to the previous Monday so the grid starts clean
    while (startDate.getDay() !== 1) {
      startDate.setDate(startDate.getDate() - 1);
    }

    const endDate = new Date(today);

    // Build columns (weeks)
    const weeks: { date: string; count: number }[][] = [];
    const cur = new Date(startDate);
    let week: { date: string; count: number }[] = [];

    // Fill empty cells for days before startDate in the first week
    for (let d = 0; d < startDate.getDay() - 1; d++) {
      week.push({ date: "", count: -1 });
    }

    const monthLabelList: { weekIndex: number; label: string }[] = [];
    let lastMonth = -1;

    while (cur <= endDate) {
      const dateStr = formatDate(cur);
      const cnt = countMap.get(dateStr) ?? 0;

      if (week.length === 7) {
        weeks.push(week);
        week = [];
      }
      week.push({ date: dateStr, count: cnt });

      const curMonth = cur.getMonth();
      if (curMonth !== lastMonth && week.length > 0) {
        monthLabelList.push({
          weekIndex: weeks.length,
          label: getMonthLabel(cur),
        });
        lastMonth = curMonth;
      }

      cur.setDate(cur.getDate() + 1);
    }

    // Fill remaining cells in the last week
    while (week.length < 7) {
      week.push({ date: "", count: -1 });
    }
    weeks.push(week);

    const allCounts = weeks.flat().filter((c) => c.count >= 0).map((c) => c.count);
    const max = Math.max(...allCounts, 1);

    return { grid: weeks, monthLabels: monthLabelList, maxCount: max };
  }, [data, months]);

  const cellSize = 13;
  const gap = 3;

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        alignItems: "flex-start",
        fontFamily: '"Fira Sans", "Roboto", sans-serif',
      }}
      data-testid="heatmap"
    >
      {/* Month labels row */}
      <div
        style={{
          display: "flex",
          marginLeft: 30,
          marginBottom: 4,
          height: 18,
        }}
      >
        {monthLabels.map((ml, i) => {
          const prevPos = i > 0 ? monthLabels[i - 1].weekIndex : 0;
          const pos = ml.weekIndex;
          const offset = pos - prevPos;
          return (
            <div
              key={ml.label + i}
              style={{
                width: offset * (cellSize + gap) - gap,
                fontSize: 11,
                color: "#64748B",
              }}
            >
              {ml.label}
            </div>
          );
        })}
      </div>

      <div style={{ display: "flex" }}>
        {/* Day labels */}
        <div
          style={{
            display: "flex",
            flexDirection: "column",
            marginRight: 6,
            gap,
          }}
        >
          {DAY_LABELS.map((label, i) => (
            <div
              key={i}
              style={{
                width: 24,
                height: cellSize,
                fontSize: 10,
                color: label ? "#94A3B8" : "transparent",
                display: "flex",
                alignItems: "center",
              }}
            >
              {label}
            </div>
          ))}
        </div>

        {/* Grid */}
        <div
          style={{
            display: "grid",
            gridAutoFlow: "column",
            gridTemplateRows: `repeat(7, ${cellSize}px)`,
            gap,
          }}
        >
          {grid.flat().map((cell, i) => (
            <div
              key={i}
              data-date={cell.date || undefined}
              data-count={cell.count >= 0 ? cell.count : undefined}
              style={{
                width: cellSize,
                height: cellSize,
                borderRadius: 3,
                backgroundColor:
                  cell.count < 0 ? "transparent" : getColor(cell.count, maxCount),
              }}
              title={
                cell.date
                  ? `${cell.date}: ${cell.count} submission${cell.count !== 1 ? "s" : ""}`
                  : undefined
              }
            />
          ))}
        </div>
      </div>

      {/* Legend */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          marginTop: 8,
          marginLeft: 30,
          gap: 4,
          fontSize: 11,
          color: "#64748B",
        }}
      >
        <span>Less</span>
        {[0, 0.25, 0.5, 0.75, 1].map((ratio) => (
          <div
            key={ratio}
            style={{
              width: cellSize,
              height: cellSize,
              borderRadius: 3,
              backgroundColor: getColor(
                ratio === 0 ? 0 : Math.ceil(ratio * maxCount),
                maxCount,
              ),
            }}
          />
        ))}
        <span>More</span>
      </div>
    </div>
  );
};

export default Heatmap;
