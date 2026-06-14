// ============================================================
// Records service
// ============================================================

import api from "./api";
import type { PaginatedResponse } from "../types/api";
import type { SubmissionRecord, DailyStats, Summary, RecordListQuery } from "../types/record";

const RECORDS = "/records";

export async function getRecords(query: RecordListQuery = {}): Promise<PaginatedResponse<SubmissionRecord>> {
  const resp = await api.get<PaginatedResponse<SubmissionRecord>>(RECORDS, { params: query });
  return resp.data;
}

export async function getDailyStats(userId: number): Promise<DailyStats[]> {
  const resp = await api.get<DailyStats[]>(`${RECORDS}/stats/daily`, {
    params: { user_id: userId },
  });
  return resp.data;
}

export async function getSummary(userId: number): Promise<Summary> {
  const resp = await api.get<Summary>(`${RECORDS}/summary`, {
    params: { user_id: userId },
  });
  return resp.data;
}
