// ============================================================
// Problem types
// ============================================================
// Matches backend Prisma schema (see backend/prisma/schema.prisma Problem model).
// ProblemDetail.tsx also defines a local ApiProblem mirroring this shape.

export interface Problem {
  id: string;
  title: string;
  sourcePlatform: string;
  sourceId: string;
  sourceUrl: string;
  difficultyRaw: string;
  difficultyNormalized: number;
  tagsPlatform: number[];
  tagsNormalized: string[];
  fullContent?: string;
  solutionSummary?: string;
  solutions?: ProblemSolution[];
  createdAt: string;
  updatedAt: string;
}

export interface ProblemSolution {
  id: string;
  problemId: string;
  solutionIndex: number;
  content: string;
  author?: string;
  sourceUrl?: string;
  createdAt: string;
  updatedAt: string;
}

export interface ProblemListQuery {
  page?: number;
  limit?: number;
  search?: string;
  platform?: string;
  difficultyMin?: number;
  difficultyMax?: number;
  tags?: string[];
  sortBy?: string;
  order?: "asc" | "desc";
}

export interface ProblemSearchResult {
  problem: Problem;
  score: number;
}

// ─── Vector / RAG search ────────────────────────────────────────────

/** Request body for POST /api/problems/search/vector */
export interface VectorSearchRequest {
  query: string;
  topK?: number;
  platform?: string;
  tags?: string;
  difficultyMin?: number;
  difficultyMax?: number;
}

/** One search result row — matches problem row from ANN search on solution_summary vector */
export interface VectorSearchResultItem {
  id: string;
  title: string;
  sourcePlatform: string;
  sourceId: string;
  difficultyNormalized: number;
  tagsNormalized: string[];
  solutionSummary: string | null;
  similarity: number;
  // New optional fields for RAG v1 (backward compatible)
  retrievalSummary?: string;
  sparseText?: string;
  scores?: {
    contentScore: number;
    solutionScore: number;
    keywordScore: number;
    roughScore: number;
    rerankScore?: number;
  };
  matched?: {
    keywords: string[];
    sources: string[];
  };
}

/** Full response from POST /api/problems/search/vector */
export interface VectorSearchResponse {
  query: string;
  queryAnalysis?: {
    queryType: string;
    expandedQuery: string;
    algorithmTerms: string[];
    weights: Record<string, number>;
  };
  results: VectorSearchResultItem[];
  total: number;
}
