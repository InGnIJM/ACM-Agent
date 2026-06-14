// Training service
import api from "./api";
import type { TrainingPlan, RecommendResult } from "../types/training";

const TRAINING = "/training";

export async function getPlan(userId: string): Promise<TrainingPlan> {
  const resp = await api.get<TrainingPlan>(`${TRAINING}/plans/${userId}`);
  return resp.data;
}

export async function generatePlan(userId: string): Promise<TrainingPlan> {
  const resp = await api.post<TrainingPlan>(`${TRAINING}/plans/${userId}/generate`);
  return resp.data;
}

export async function getRecommend(): Promise<RecommendResult> {
  const resp = await api.get<RecommendResult>(`${TRAINING}/recommend`);
  return resp.data;
}
