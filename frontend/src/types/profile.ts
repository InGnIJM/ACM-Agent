// ============================================================
// Profile types
// ============================================================

import type { DailyStats, Summary } from "./record";

export interface SkillRadar {
  label: string;
  value: number; // 0-100
}

export interface WeaknessItem {
  tag: string;
  failure_rate: number;
  suggestion: string;
}

export interface Profile {
  id: number;
  user_id: number;
  summary: Summary;
  daily_stats: DailyStats[];
  skill_radar: SkillRadar[];
  strengths: string[];
  weaknesses: WeaknessItem[];
  generated_at: string;
}

export interface ProfileGenerateRequest {
  user_id: number;
  days?: number; // how many days of history to analyse, default 90
}
