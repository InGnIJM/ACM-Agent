// ============================================================
// Team / Matching types
// ============================================================

export interface TeamMember {
  user_id: number;
  username: string;
  nickname?: string;
  avatar_url?: string;
  role: "leader" | "member";
  joined_at: string;
}

export interface Team {
  id: number;
  name: string;
  description?: string;
  leader_id: number;
  members: TeamMember[];
  tags: string[];
  max_members: number;
  status: "recruiting" | "full" | "inactive";
  created_at: string;
  updated_at: string;
}

export interface CreateTeamRequest {
  name: string;
  description?: string;
  tags?: string[];
  max_members?: number;
}

export interface MatchProfile {
  user_id: number;
  username: string;
  nickname?: string;
  avatar_url?: string;
  solved_count: number;
  strengths: string[];
  weaknesses: string[];
  score: number;
}

export interface MatchRecommendResult {
  user_id: number;
  matches: MatchProfile[];
  generated_at: string;
}
