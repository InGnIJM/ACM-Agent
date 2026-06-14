// ============================================================
// Training plan types
// ============================================================

export interface TrainingTask {
  day: number;
  problem_count: number;
  topics: string[];
  difficulty_distribution: {
    easy: number;
    medium: number;
    hard: number;
  };
  notes?: string;
}

export interface TrainingPlan {
  id: number;
  user_id: number;
  name: string;
  description?: string;
  duration_days: number;
  tasks: TrainingTask[];
  generated_at: string;
  expires_at?: string;
}

export interface RecommendedProblem {
  problem_id: number;
  problem_title: string;
  difficulty: string;
  platform: string;
  tags: string[];
  reason: string;
  priority: number; // 0-100, higher = more recommended
}

export interface RecommendResult {
  user_id: number;
  items: RecommendedProblem[];
  generated_at: string;
}
