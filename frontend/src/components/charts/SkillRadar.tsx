import React from "react";
import {
  RadarChart,
  PolarGrid,
  PolarAngleAxis,
  PolarRadiusAxis,
  Radar,
  ResponsiveContainer,
} from "recharts";

export interface SkillRadarDataPoint {
  tag: string;
  score: number;
}

export interface SkillRadarProps {
  data: SkillRadarDataPoint[];
  maxValue?: number;
  size?: number;
  color?: string;
}

const SkillRadar: React.FC<SkillRadarProps> = ({
  data,
  maxValue,
  size = 300,
  color = "#1E40AF",
}) => {
  const computedMax = maxValue ?? Math.max(...data.map((d) => d.score), 1);

  return (
    <ResponsiveContainer width="100%" height={size}>
      <RadarChart data={data} cx="50%" cy="50%" outerRadius="70%">
        <PolarGrid stroke="#E2E8F0" />
        <PolarAngleAxis
          dataKey="tag"
          tick={{ fontSize: 12, fill: "#64748B" }}
        />
        <PolarRadiusAxis
          angle={30}
          domain={[0, computedMax]}
          tick={{ fontSize: 10, fill: "#94A3B8" }}
        />
        <Radar
          name="Skills"
          dataKey="score"
          stroke={color}
          fill={color}
          fillOpacity={0.25}
          strokeWidth={2}
        />
      </RadarChart>
    </ResponsiveContainer>
  );
};

export default SkillRadar;
