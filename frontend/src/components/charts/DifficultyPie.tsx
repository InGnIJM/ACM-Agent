import React from "react";
import {
  PieChart,
  Pie,
  Cell,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from "recharts";

export interface DifficultyPieDataPoint {
  difficulty: string;
  count: number;
}

export interface DifficultyPieProps {
  data: DifficultyPieDataPoint[];
}

/** Difficulty bands mapped to colors: easier = green, harder = red */
const DIFFICULTY_COLORS: Record<string, string> = {
  Easy: "#2E7D32",
  "Medium-Easy": "#66BB6A",
  Medium: "#FBC02D",
  "Medium-Hard": "#F57C00",
  Hard: "#C62828",
};

const DEFAULT_COLORS = [
  "#1E40AF",
  "#3B82F6",
  "#60A5FA",
  "#93C5FD",
  "#DBEAFE",
  "#7C3AED",
  "#A78BFA",
  "#F59E0B",
  "#EF4444",
  "#10B981",
];

const getColor = (difficulty: string, index: number): string => {
  return DIFFICULTY_COLORS[difficulty] ?? DEFAULT_COLORS[index % DEFAULT_COLORS.length];
};

const DifficultyPie: React.FC<DifficultyPieProps> = ({ data }) => {
  return (
    <ResponsiveContainer width="100%" height={320}>
      <PieChart>
        <Pie
          data={data}
          dataKey="count"
          nameKey="difficulty"
          cx="50%"
          cy="50%"
          outerRadius={110}
          innerRadius={50}
          paddingAngle={2}
          label={({ difficulty, count, percent }) =>
            `${difficulty}: ${count} (${(percent * 100).toFixed(0)}%)`
          }
          labelLine={{ stroke: "#94A3B8" }}
        >
          {data.map((entry, index) => (
            <Cell
              key={entry.difficulty}
              fill={getColor(entry.difficulty, index)}
            />
          ))}
        </Pie>
        <Tooltip
          contentStyle={{
            borderRadius: 8,
            border: "1px solid #E2E8F0",
            fontSize: 13,
          }}
        />
        <Legend
          verticalAlign="bottom"
          formatter={(value) => (
            <span style={{ color: "#475569", fontSize: 13 }}>{value}</span>
          )}
        />
      </PieChart>
    </ResponsiveContainer>
  );
};

export default DifficultyPie;
