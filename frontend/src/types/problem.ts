// ============================================================
// Problem types
// ============================================================

export type Difficulty = "easy" | "medium" | "hard" | "unknown";

export interface ProblemTag {
  id: number;
  name: string;
}

export interface ProblemSource {
  platform: string;
  problem_id: string;
  url: string;
}

export interface Problem {
  id: number;
  title: string;
  description?: string;
  difficulty: Difficulty;
  tags: ProblemTag[];
  sources: ProblemSource[];
  solved_count: number;
  attempted_count: number;
  created_at: string;
  updated_at: string;
}

export interface ProblemListQuery {
  page?: number;
  page_size?: number;
  difficulty?: Difficulty;
  tag?: string;
  platform?: string;
  sort_by?: string;
  order?: "asc" | "desc";
}

export interface ProblemSearchResult {
  problem: Problem;
  score: number;
}
