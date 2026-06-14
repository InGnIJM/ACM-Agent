// Matching + Teams services
import api from "./api";
import type { Team, CreateTeamRequest, MatchProfile } from "../types/team";

const MATCHING = "/matching";
const TEAMS = "/teams";

/** Get recommended teammates for a user. */
export async function recommend(userId: string): Promise<MatchProfile[]> {
  const resp = await api.post<MatchProfile[]>(`${MATCHING}/recommend/${userId}`);
  return resp.data;
}

/** Get compatibility between two users. */
export async function getCompatibility(userId: string, targetId: string) {
  const resp = await api.get(`${MATCHING}/compatibility/${userId}/${targetId}`);
  return resp.data;
}

export async function getTeams(): Promise<Team[]> {
  const resp = await api.get<Team[]>(TEAMS);
  return resp.data;
}

export async function createTeam(data: CreateTeamRequest): Promise<Team> {
  const resp = await api.post<Team>(TEAMS, data);
  return resp.data;
}

export async function getTeam(id: string): Promise<Team> {
  const resp = await api.get<Team>(`${TEAMS}/${id}`);
  return resp.data;
}

export async function addMember(teamId: string, userId: string): Promise<Team> {
  const resp = await api.post<Team>(`${TEAMS}/${teamId}/members`, { userId });
  return resp.data;
}

export async function removeMember(teamId: string, userId: string): Promise<void> {
  await api.delete(`${TEAMS}/${teamId}/members/${userId}`);
}

export async function archiveTeam(teamId: string): Promise<Team> {
  const resp = await api.patch<Team>(`${TEAMS}/${teamId}/archive`);
  return resp.data;
}
