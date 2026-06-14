import React from "react";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from "recharts";

export interface DailyTrendDataPoint {
  date: string;
  acCount: number;
  submitCount: number;
}

export interface DailyTrendProps {
  data: DailyTrendDataPoint[];
  days?: number;
}

const DailyTrend: React.FC<DailyTrendProps> = ({ data, days }) => {
  const displayData = days ? data.slice(-days) : data;

  return (
    <ResponsiveContainer width="100%" height={300}>
      <LineChart
        data={displayData}
        margin={{ top: 5, right: 20, left: 0, bottom: 5 }}
      >
        <CartesianGrid strokeDasharray="3 3" stroke="#E2E8F0" />
        <XAxis
          dataKey="date"
          tick={{ fontSize: 11, fill: "#64748B" }}
          interval="preserveStartEnd"
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
        <Legend />
        <Line
          type="monotone"
          dataKey="submitCount"
          stroke="#94A3B8"
          strokeWidth={2}
          dot={false}
          name="Total Submissions"
        />
        <Line
          type="monotone"
          dataKey="acCount"
          stroke="#1E40AF"
          strokeWidth={2}
          dot={false}
          name="AC Count"
        />
      </LineChart>
    </ResponsiveContainer>
  );
};

export default DailyTrend;
