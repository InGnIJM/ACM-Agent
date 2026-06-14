// ============================================================
// Training record types
// ============================================================

export type RecordStatus = "accepted" | "wrong_answer" | "time_limit" | "memory_limit" | "runtime_error" | "compilation_error" | "pending";

export interface SubmissionRecord {
  id: number;
  user_id: number;
  problem_id: number;
  problem_title?: string;
  platform: string;
  difficulty: string;
  status: RecordStatus;
  runtime_ms?: number;
  memory_kb?: number;
  language: string;
  submitted_at: string;
  created_at: string;
}

export interface DailyStats {
  date: string;
  total: number;
  accepted: number;
  easy: number;
  medium: number;
  hard: number;
}

export interface Summary {
  total_solved: number;
  total_attempted: number;
  acceptance_rate: number;
  streak_days: number;
  longest_streak: number;
  coins_earned: number;
  credits_earned: number;
  rank?: string;
  percentile?: number;
  by_difficulty: {
    easy: SolvedCount;
    medium: SolvedCount;
    hard: SolvedCount;
  };
  by_platform: Record<string, SolvedCount>;
}

export interface SolvedCount {
  solved: number;
  attempted: number;
}

export interface RecordListQuery {
  page?: number;
  page_size?: number;
  user_id?: number;
  status?: RecordStatus;
  difficulty?: string;
  platform?: string;
  date_from?: string;
  date_to?: string;
  sort_by?: string;
  order?: "asc" | "desc";
}
