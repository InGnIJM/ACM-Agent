import React from "react";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "recharts";

export interface TagBarDataPoint {
  tag: string;
  count: number;
}

export interface TagBarProps {
  data: TagBarDataPoint[];
}

/** Color bands for bar indices — cycle through these */
const BAR_COLORS = [
  "#1E40AF",
  "#3B82F6",
  "#60A5FA",
  "#7C3AED",
  "#A78BFA",
  "#F59E0B",
  "#EF4444",
  "#10B981",
];

const TagBar: React.FC<TagBarProps> = ({ data }) => {
  return (
    <ResponsiveContainer width="100%" height={320}>
      <BarChart
        data={data}
        margin={{ top: 5, right: 20, left: 0, bottom: 5 }}
      >
        <CartesianGrid strokeDasharray="3 3" stroke="#E2E8F0" />
        <XAxis
          dataKey="tag"
          tick={{ fontSize: 11, fill: "#64748B" }}
          interval={0}
        />
        <YAxis
          allowDecimals={false}
          tick={{ fontSize: 11, fill: "#94A3B8" }}
        />
        <Tooltip
          contentStyle={{
            borderRadius: 8,
            border: "1px solid #E2E8F0",
            fontSize: 13,
          }}
        />
        <Bar dataKey="count" name="Problems" radius={[4, 4, 0, 0]}>
          {data.map((entry, index) => (
            <rect key={entry.tag} fill={BAR_COLORS[index % BAR_COLORS.length]} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
};

export default TagBar;
