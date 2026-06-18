// ============================================================
// Problems service
// ============================================================

import api from "./api";
import type { PaginatedResponse } from "../types/api";
import type { Problem, ProblemListQuery, ProblemSearchResult, VectorSearchRequest, VectorSearchResponse } from "../types/problem";

const PROBLEMS = "/problems";

export async function getProblems(query: ProblemListQuery = {}): Promise<PaginatedResponse<Problem>> {
  const resp = await api.get<PaginatedResponse<Problem>>(PROBLEMS, { params: query });
  return resp.data;
}

export async function getProblem(id: string): Promise<Problem> {
  const resp = await api.get<Problem>(`${PROBLEMS}/${id}`);
  return resp.data;
}

export async function searchProblems(q: string): Promise<ProblemSearchResult[]> {
  const resp = await api.get<ProblemSearchResult[]>(`${PROBLEMS}/search`, {
    params: { q },
  });
  return resp.data;
}

export async function getSimilarProblems(id: string): Promise<Problem[]> {
  const resp = await api.get<Problem[]>(`${PROBLEMS}/${id}/similar`);
  return resp.data;
}

/** Semantic vector search — POST /api/problems/search/vector */
export async function searchByVector(dto: VectorSearchRequest): Promise<VectorSearchResponse> {
  const resp = await api.post<VectorSearchResponse>(`${PROBLEMS}/search/vector`, dto);
  return resp.data;
}

export async function deleteProblem(id: string): Promise<void> {
  await api.delete(`${PROBLEMS}/${id}`);
}

export async function batchDeleteProblems(ids: string[]): Promise<{ deleted: boolean; count: number }> {
  const resp = await api.post<{ deleted: boolean; count: number }>(`${PROBLEMS}/batch-delete`, { ids });
  return resp.data;
}
