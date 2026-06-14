// ============================================================
// Problems service
// ============================================================

import api from "./api";
import type { PaginatedResponse } from "../types/api";
import type { Problem, ProblemListQuery } from "../types/problem";

const PROBLEMS = "/problems";

export async function getProblems(query: ProblemListQuery = {}): Promise<PaginatedResponse<Problem>> {
  const resp = await api.get<PaginatedResponse<Problem>>(PROBLEMS, { params: query });
  return resp.data;
}

export async function getProblem(id: number): Promise<Problem> {
  const resp = await api.get<Problem>(`${PROBLEMS}/${id}`);
  return resp.data;
}

export interface ProblemSearchResult {
  problem: Problem;
  score: number;
}

export async function searchProblems(q: string): Promise<ProblemSearchResult[]> {
  const resp = await api.get<ProblemSearchResult[]>(`${PROBLEMS}/search`, {
    params: { q },
  });
  return resp.data;
}

export async function getSimilarProblems(id: number): Promise<Problem[]> {
  const resp = await api.get<Problem[]>(`${PROBLEMS}/${id}/similar`);
  return resp.data;
}
