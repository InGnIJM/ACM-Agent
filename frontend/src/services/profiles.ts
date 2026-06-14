// Profiles service
import api from "./api";
import type { Profile } from "../types/profile";

const PROFILES = "/profiles";

export async function getProfile(userId: string): Promise<Profile> {
  const resp = await api.get<Profile>(`${PROFILES}/${userId}`);
  return resp.data;
}

export async function generateProfile(userId: string): Promise<Profile> {
  const resp = await api.post<Profile>(`${PROFILES}/${userId}/generate`);
  return resp.data;
}
