// ─── Matching Algorithm ──────────────────────────────────────────────────────
// Pure functions for teammate compatibility scoring and recommendation,
// plus NestJS service layer that loads data from Prisma and delegates.

import { Injectable } from '@nestjs/common';
import { PrismaService } from '../common/prisma/prisma.service';

// ─── Types ──────────────────────────────────────────────────────────────────

/** Subset of Prisma UserProfile fields consumed by the matching algorithm. */
export interface ProfileSnapshot {
  userId: string;
  strengths: string[] | null;
  weaknesses: string[] | null;
  overallScore: number;
  style: string | null;
  [key: string]: unknown; // allow extra Prisma fields
}

export interface PairComplement {
  skillComplement: number;
  levelProximity: number;
  styleDiversity: number;
}

export interface TeammateResult {
  teammates: [ProfileSnapshot, ProfileSnapshot];
  teamScore: number;
  pairScores: [number, number, number]; // [user-t1, user-t2, t1-t2]
  complementDetails: PairComplement;
  skillCoverageRatio: number;
}

// ─── Constants ──────────────────────────────────────────────────────────────

const SKILL_WEIGHT = 0.5;
const LEVEL_WEIGHT = 0.3;
const STYLE_WEIGHT = 0.2;

const TEAM_PAIR_WEIGHT = 0.7;
const TEAM_COVERAGE_WEIGHT = 0.3;

const STYLE_PAIRS: Record<string, number> = {
  grinder_deep_diver: 1.0,
  grinder_specialist: 0.8,
  deep_diver_specialist: 0.9,
  balanced_grinder: 0.7,
  balanced_deep_diver: 0.7,
  balanced_specialist: 0.7,
  balanced_balanced: 0.5,
};

// ─── Helpers ────────────────────────────────────────────────────────────────

function safeArray(arr: string[] | null | undefined): string[] {
  return Array.isArray(arr) ? arr : [];
}

function intersection(a: string[], b: string[]): number {
  const setB = new Set(b);
  let count = 0;
  for (const item of a) {
    if (setB.has(item)) count++;
  }
  return count;
}

function unionSize(arrays: string[][]): number {
  const set = new Set<string>();
  for (const arr of arrays) {
    for (const item of arr) {
      set.add(item);
    }
  }
  return set.size;
}

function lookupStyle(a: string | null, b: string | null): number {
  const sa = (a ?? '').trim().toLowerCase();
  const sb = (b ?? '').trim().toLowerCase();
  // Try both orderings since STYLE_PAIRS keys are not alphabetically sorted
  return STYLE_PAIRS[`${sa}_${sb}`] ?? STYLE_PAIRS[`${sb}_${sa}`] ?? 0.5;
}

function round3(n: number): number {
  return Math.round(n * 1000) / 1000;
}

// ─── 1. calcCompatibility ───────────────────────────────────────────────────

/**
 * Compute pairwise compatibility between two user profiles.
 *
 * Returns a number in [0, 1] fixed to 3 decimal places.
 *
 * Formula:
 *   skillComplement * SKILL_WEIGHT  (0.5)
 * + levelProximity  * LEVEL_WEIGHT  (0.3)
 * + styleDiversity  * STYLE_WEIGHT  (0.2)
 */
export function calcCompatibility(a: ProfileSnapshot, b: ProfileSnapshot): number {
  const aStrengths = safeArray(a.strengths);
  const bStrengths = safeArray(b.strengths);
  const aWeaknesses = safeArray(a.weaknesses);
  const bWeaknesses = safeArray(b.weaknesses);

  // Skill complement
  const complementCount =
    intersection(aStrengths, bWeaknesses) +
    intersection(bStrengths, aWeaknesses);
  const strengthSum = aStrengths.length + bStrengths.length;
  const skillComplement = complementCount / Math.max(strengthSum, 1);

  // Level proximity
  const levelProximity = Math.max(
    0,
    1 - Math.abs(a.overallScore - b.overallScore) * 2,
  );

  // Style diversity
  const styleDiversity = lookupStyle(a.style, b.style);

  const result =
    skillComplement * SKILL_WEIGHT +
    levelProximity * LEVEL_WEIGHT +
    styleDiversity * STYLE_WEIGHT;

  return round3(result);
}

// ─── 2. calcTeamScore ───────────────────────────────────────────────────────

/**
 * Compute team score for exactly three users.
 *
 * Returns a number in [0, 1].
 *
 * Formula:
 *   avg of 3 pair compatibility scores * TEAM_PAIR_WEIGHT  (0.7)
 * + skill coverage ratio             * TEAM_COVERAGE_WEIGHT (0.3)
 *
 * Skill coverage = |union of all strengths| / 10, capped at 1.
 */
export function calcTeamScore(users: ProfileSnapshot[]): number {
  if (users.length !== 3) {
    throw new Error(`calcTeamScore requires exactly 3 users, got ${users.length}`);
  }

  const [u0, u1, u2] = users;

  const pair01 = calcCompatibility(u0, u1);
  const pair02 = calcCompatibility(u0, u2);
  const pair12 = calcCompatibility(u1, u2);

  const avgPair = (pair01 + pair02 + pair12) / 3;

  const allStrengths = users.map((u) => safeArray(u.strengths));
  const coverage = unionSize(allStrengths);
  const coverageRatio = Math.min(coverage / 10, 1);

  const result = avgPair * TEAM_PAIR_WEIGHT + coverageRatio * TEAM_COVERAGE_WEIGHT;

  return round3(result);
}

// ─── 3. recommendTeammates ──────────────────────────────────────────────────

/**
 * Recommend top-K teammate pairs for a given user.
 *
 * Algorithm:
 *   1. Filter out self and excluded users.
 *   2. Compute pair compatibility with every candidate, take top 10.
 *   3. Enumerate all C(10,2)=45 trios, score each via calcTeamScore.
 *   4. Sort descending, return topK.
 */
export function recommendTeammates(
  user: ProfileSnapshot,
  candidates: ProfileSnapshot[],
  topK = 5,
  excludeUserIds: string[] = [],
): TeammateResult[] {
  // Build exclusion set
  const exclude = new Set([user.userId, ...excludeUserIds]);

  // Step 1 — filter candidates
  const eligible = candidates.filter((c) => !exclude.has(c.userId));

  // Step 2 — pair scores with user, sort, take top 10
  const scored = eligible
    .map((c) => ({
      candidate: c,
      score: calcCompatibility(user, c),
    }))
    .sort((a, b) => b.score - a.score);

  const topCandidates = scored.slice(0, 10).map((s) => s.candidate);

  if (topCandidates.length < 2) {
    return []; // not enough candidates to form a trio
  }

  // Step 3 — enumerate all C(n,2) trios
  const trios: {
    teammates: [ProfileSnapshot, ProfileSnapshot];
    teamScore: number;
    pairScores: [number, number, number];
    complementDetails: PairComplement;
    skillCoverageRatio: number;
  }[] = [];

  for (let i = 0; i < topCandidates.length - 1; i++) {
    for (let j = i + 1; j < topCandidates.length; j++) {
      const t1 = topCandidates[i];
      const t2 = topCandidates[j];

      const trio = [user, t1, t2];
      const teamScore = calcTeamScore(trio);

      const p01 = calcCompatibility(user, t1);
      const p02 = calcCompatibility(user, t2);
      const p12 = calcCompatibility(t1, t2);

      // Complement details averaged across all 3 pairs
      const sStrengths = safeArray(user.strengths);
      const t1Strengths = safeArray(t1.strengths);
      const t2Strengths = safeArray(t2.strengths);
      const sWeaknesses = safeArray(user.weaknesses);
      const t1Weaknesses = safeArray(t1.weaknesses);
      const t2Weaknesses = safeArray(t2.weaknesses);

      // Skill complement per pair
      const sc01 =
        (intersection(sStrengths, t1Weaknesses) +
          intersection(t1Strengths, sWeaknesses)) /
        Math.max(sStrengths.length + t1Strengths.length, 1);
      const sc02 =
        (intersection(sStrengths, t2Weaknesses) +
          intersection(t2Strengths, sWeaknesses)) /
        Math.max(sStrengths.length + t2Strengths.length, 1);
      const sc12 =
        (intersection(t1Strengths, t2Weaknesses) +
          intersection(t2Strengths, t1Weaknesses)) /
        Math.max(t1Strengths.length + t2Strengths.length, 1);
      const avgSkillComplement = (sc01 + sc02 + sc12) / 3;

      // Level proximity per pair
      const lp01 = Math.max(0, 1 - Math.abs(user.overallScore - t1.overallScore) * 2);
      const lp02 = Math.max(0, 1 - Math.abs(user.overallScore - t2.overallScore) * 2);
      const lp12 = Math.max(0, 1 - Math.abs(t1.overallScore - t2.overallScore) * 2);
      const avgLevelProximity = (lp01 + lp02 + lp12) / 3;

      // Style diversity per pair
      const sd01 = lookupStyle(user.style, t1.style);
      const sd02 = lookupStyle(user.style, t2.style);
      const sd12 = lookupStyle(t1.style, t2.style);
      const avgStyleDiversity = (sd01 + sd02 + sd12) / 3;

      // Skill coverage for the trio
      const coverage = unionSize([sStrengths, t1Strengths, t2Strengths]);
      const coverageRatio = Math.min(coverage / 10, 1);

      trios.push({
        teammates: [t1, t2],
        teamScore,
        pairScores: [round3(p01), round3(p02), round3(p12)],
        complementDetails: {
          skillComplement: round3(avgSkillComplement),
          levelProximity: round3(avgLevelProximity),
          styleDiversity: round3(avgStyleDiversity),
        },
        skillCoverageRatio: round3(coverageRatio),
      });
    }
  }

  // Step 4 — sort by teamScore descending, return topK
  trios.sort((a, b) => b.teamScore - a.teamScore);

  return trios.slice(0, topK);
}

// ─── 4. NestJS MatchingService ──────────────────────────────────────────────

function toProfileSnapshot(prismaProfile: {
  userId: string;
  strengths: unknown;
  weaknesses: unknown;
  overallScore: number;
  style: string | null;
}): ProfileSnapshot {
  return {
    userId: prismaProfile.userId,
    strengths: Array.isArray(prismaProfile.strengths)
      ? (prismaProfile.strengths as string[])
      : null,
    weaknesses: Array.isArray(prismaProfile.weaknesses)
      ? (prismaProfile.weaknesses as string[])
      : null,
    overallScore: prismaProfile.overallScore,
    style: prismaProfile.style,
  };
}

interface RecommendCandidate {
  userId: string;
  username: string;
  nickname: string | null;
  overallScore: number;
  strengths: string[] | null;
  weaknesses: string[] | null;
  style: string | null;
  compatibility: number;
}

export interface RecommendItem {
  teammates: RecommendCandidate[];
  teamScore: number;
  pairScores: [number, number, number];
  complementDetails: PairComplement;
  skillCoverageRatio: number;
}

export interface CompatibilityDetail {
  user: {
    userId: string;
    username: string;
    nickname: string | null;
    overallScore: number;
    strengths: string[] | null;
    weaknesses: string[] | null;
    style: string | null;
  };
  target: {
    userId: string;
    username: string;
    nickname: string | null;
    overallScore: number;
    strengths: string[] | null;
    weaknesses: string[] | null;
    style: string | null;
  };
  compatibility: number;
  breakdown: {
    skillComplement: number;
    levelProximity: number;
    styleDiversity: number;
  };
}

@Injectable()
export class MatchingService {
  constructor(private readonly prisma: PrismaService) {}

  /** Recommend top teammate pairs for a user. */
  async recommend(userId: string): Promise<RecommendItem[]> {
    const ownProfile = await this.prisma.userProfile.findUnique({
      where: { userId },
    });
    if (!ownProfile) {
      return [];
    }
    const user = toProfileSnapshot(ownProfile);

    const allProfiles = await this.prisma.userProfile.findMany({
      where: { userId: { not: userId } },
    });

    const candidates = allProfiles.map(toProfileSnapshot);
    const results = recommendTeammates(user, candidates);

    // Resolve usernames for all candidate userIds referenced in results
    const userIdSet = new Set<string>();
    for (const r of results) {
      userIdSet.add(r.teammates[0].userId);
      userIdSet.add(r.teammates[1].userId);
    }
    userIdSet.add(userId);

    const users = await this.prisma.user.findMany({
      where: { id: { in: [...userIdSet] } },
      select: { id: true, username: true, nickname: true },
    });
    const userMap = new Map(users.map((u) => [u.id, u]));

    const me = userMap.get(userId)!;

    return results.map((r) => {
      const t1User = userMap.get(r.teammates[0].userId)!;
      const t2User = userMap.get(r.teammates[1].userId)!;
      const t1Snap = r.teammates[0];
      const t2Snap = r.teammates[1];

      return {
        teammates: [
          {
            userId: me.id,
            username: me.username,
            nickname: me.nickname,
            overallScore: ownProfile.overallScore,
            strengths: ownProfile.strengths as string[] | null,
            weaknesses: ownProfile.weaknesses as string[] | null,
            style: ownProfile.style,
            compatibility: r.pairScores[0],
          },
          {
            userId: t1User.id,
            username: t1User.username,
            nickname: t1User.nickname,
            overallScore: t1Snap.overallScore,
            strengths: t1Snap.strengths,
            weaknesses: t1Snap.weaknesses,
            style: t1Snap.style,
            compatibility: r.pairScores[1],
          },
          {
            userId: t2User.id,
            username: t2User.username,
            nickname: t2User.nickname,
            overallScore: t2Snap.overallScore,
            strengths: t2Snap.strengths,
            weaknesses: t2Snap.weaknesses,
            style: t2Snap.style,
            compatibility: r.pairScores[2],
          },
        ],
        teamScore: r.teamScore,
        pairScores: r.pairScores,
        complementDetails: r.complementDetails,
        skillCoverageRatio: r.skillCoverageRatio,
      };
    });
  }

  /** Get detailed compatibility breakdown between two users. */
  async getCompatibility(
    userId: string,
    targetId: string,
  ): Promise<CompatibilityDetail> {
    const [ownProfile, targetProfile] = await Promise.all([
      this.prisma.userProfile.findUnique({ where: { userId } }),
      this.prisma.userProfile.findUnique({ where: { userId: targetId } }),
    ]);

    if (!ownProfile) {
      throw new Error(`No profile found for user ${userId}`);
    }
    if (!targetProfile) {
      throw new Error(`No profile found for user ${targetId}`);
    }

    const a = toProfileSnapshot(ownProfile);
    const b = toProfileSnapshot(targetProfile);
    const compatibility = calcCompatibility(a, b);

    const aStrengths = safeArray(a.strengths);
    const bStrengths = safeArray(b.strengths);
    const aWeaknesses = safeArray(a.weaknesses);
    const bWeaknesses = safeArray(b.weaknesses);

    const complementCount =
      intersection(aStrengths, bWeaknesses) +
      intersection(bStrengths, aWeaknesses);
    const strengthSum = aStrengths.length + bStrengths.length;
    const skillComplement = strengthSum > 0
      ? round3(complementCount / strengthSum)
      : 0;

    const levelProximity = round3(
      Math.max(0, 1 - Math.abs(a.overallScore - b.overallScore) * 2),
    );

    const styleDiversity = lookupStyle(a.style, b.style);

    const users = await this.prisma.user.findMany({
      where: { id: { in: [userId, targetId] } },
      select: { id: true, username: true, nickname: true },
    });
    const userMap = new Map(users.map((u) => [u.id, u]));
    const me = userMap.get(userId)!;
    const target = userMap.get(targetId)!;

    return {
      user: {
        userId: me.id,
        username: me.username,
        nickname: me.nickname,
        overallScore: ownProfile.overallScore,
        strengths: ownProfile.strengths as string[] | null,
        weaknesses: ownProfile.weaknesses as string[] | null,
        style: ownProfile.style,
      },
      target: {
        userId: target.id,
        username: target.username,
        nickname: target.nickname,
        overallScore: targetProfile.overallScore,
        strengths: targetProfile.strengths as string[] | null,
        weaknesses: targetProfile.weaknesses as string[] | null,
        style: targetProfile.style,
      },
      compatibility,
      breakdown: { skillComplement, levelProximity, styleDiversity },
    };
  }
}
