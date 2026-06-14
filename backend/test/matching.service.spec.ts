import {
  calcCompatibility,
  calcTeamScore,
  recommendTeammates,
  ProfileSnapshot,
} from '../src/matching/matching.service';

// ─── Helpers ────────────────────────────────────────────────────────────────

function makeProfile(overrides: Partial<ProfileSnapshot> = {}): ProfileSnapshot {
  return {
    userId: 'u1',
    strengths: ['dp', 'graph'],
    weaknesses: ['math', 'geometry'],
    overallScore: 0.6,
    style: 'grinder',
    ...overrides,
  };
}

// ─── 1. calcCompatibility ───────────────────────────────────────────────────

describe('calcCompatibility', () => {
  it('returns 0~1 range for typical profiles', () => {
    const a = makeProfile({ userId: 'a', strengths: ['dp'], weaknesses: ['graph'] });
    const b = makeProfile({ userId: 'b', strengths: ['graph'], weaknesses: ['dp'] });
    const result = calcCompatibility(a, b);
    expect(result).toBeGreaterThanOrEqual(0);
    expect(result).toBeLessThanOrEqual(1);
  });

  it('returns a number fixed to 3 decimal places', () => {
    const a = makeProfile({ userId: 'a' });
    const b = makeProfile({ userId: 'b' });
    const result = calcCompatibility(a, b);
    const decimals = String(result).split('.')[1]?.length ?? 0;
    expect(decimals).toBeLessThanOrEqual(3);
  });

  // ── Skill complement (weight 0.5) ──

  it('gives full skill complement when strengths perfectly complement weaknesses', () => {
    const a = makeProfile({
      userId: 'a',
      strengths: ['dp', 'graph'],
      weaknesses: ['math', 'geometry'],
      overallScore: 0.5,
      style: null,
    });
    const b = makeProfile({
      userId: 'b',
      strengths: ['math', 'geometry'],
      weaknesses: ['dp', 'graph'],
      overallScore: 0.5,
      style: null,
    });
    // skillComplement = (2+2) / max(4, 1) = 4/4 = 1.0
    // levelProximity = max(0, 1-0*2) = 1.0
    // styleDiversity = 0.5 (default, unknown pair)
    // total = 1.0*0.5 + 1.0*0.3 + 0.5*0.2 = 0.5 + 0.3 + 0.1 = 0.9
    expect(calcCompatibility(a, b)).toBe(0.9);
  });

  it('gives zero skill complement when no overlap exists', () => {
    const a = makeProfile({
      userId: 'a',
      strengths: ['dp'],
      weaknesses: ['math'],
      overallScore: 0.5,
      style: null,
    });
    const b = makeProfile({
      userId: 'b',
      strengths: ['graph'],
      weaknesses: ['geometry'],
      overallScore: 0.5,
      style: null,
    });
    // skillComplement = (0+0) / max(2, 1) = 0
    // levelProximity = 1.0 (same score)
    // styleDiversity = 0.5
    // total = 0*0.5 + 1.0*0.3 + 0.5*0.2 = 0.4
    expect(calcCompatibility(a, b)).toBe(0.4);
  });

  it('handles null strengths and weaknesses', () => {
    const a = makeProfile({
      userId: 'a',
      strengths: null,
      weaknesses: null,
    });
    const b = makeProfile({
      userId: 'b',
      strengths: null,
      weaknesses: null,
    });
    const result = calcCompatibility(a, b);
    expect(result).toBeGreaterThanOrEqual(0);
  });

  it('handles undefined strengths', () => {
    const a = { userId: 'a', strengths: undefined, weaknesses: undefined, overallScore: 0.5, style: null } as unknown as ProfileSnapshot;
    const b = { userId: 'b', strengths: undefined, weaknesses: undefined, overallScore: 0.5, style: null } as unknown as ProfileSnapshot;
    const result = calcCompatibility(a, b);
    expect(result).toBeGreaterThanOrEqual(0);
  });

  // ── Level proximity (weight 0.3) ──

  it('gives full level proximity when scores are equal', () => {
    const a = makeProfile({ userId: 'a', strengths: [], weaknesses: [], overallScore: 0.7, style: null });
    const b = makeProfile({ userId: 'b', strengths: [], weaknesses: [], overallScore: 0.7, style: null });
    // levelProximity = 1.0, skillComplement = 0, styleDiversity = 0.5
    // total = 0 + 1.0*0.3 + 0.5*0.2 = 0.4
    expect(calcCompatibility(a, b)).toBe(0.4);
  });

  it('gives zero level proximity when score difference >= 0.5', () => {
    const a = makeProfile({ userId: 'a', strengths: [], weaknesses: [], overallScore: 0.0, style: null });
    const b = makeProfile({ userId: 'b', strengths: [], weaknesses: [], overallScore: 0.5, style: null });
    // levelProximity = max(0, 1 - 0.5*2) = max(0, 0) = 0
    // skillComplement = 0, styleDiversity = 0.5 → total = 0.5 * 0.2 = 0.1
    expect(calcCompatibility(a, b)).toBe(0.1);
  });

  // ── Style diversity (weight 0.2) ──

  it('returns correct style score for known pair grinder_deep_diver', () => {
    const a = makeProfile({ userId: 'a', strengths: [], weaknesses: [], overallScore: 0.5, style: 'grinder' });
    const b = makeProfile({ userId: 'b', strengths: [], weaknesses: [], overallScore: 0.5, style: 'deep_diver' });
    // skillComplement = 0, levelProximity = 1.0, styleDiversity = 1.0
    // total = 0.5*0 + 1.0*0.3 + 1.0*0.2 = 0.5
    expect(calcCompatibility(a, b)).toBe(0.5);
  });

  it('returns correct style score for known pair grinder_specialist', () => {
    const a = makeProfile({ userId: 'a', strengths: [], weaknesses: [], overallScore: 0.5, style: 'grinder' });
    const b = makeProfile({ userId: 'b', strengths: [], weaknesses: [], overallScore: 0.5, style: 'specialist' });
    // styleDiversity = 0.8, total = 0.3 + 0.8*0.2 = 0.46
    expect(calcCompatibility(a, b)).toBe(0.46);
  });

  it('returns correct style score for known pair deep_diver_specialist', () => {
    const a = makeProfile({ userId: 'a', strengths: [], weaknesses: [], overallScore: 0.5, style: 'deep_diver' });
    const b = makeProfile({ userId: 'b', strengths: [], weaknesses: [], overallScore: 0.5, style: 'specialist' });
    // styleDiversity = 0.9, total = 0.3 + 0.9*0.2 = 0.48
    expect(calcCompatibility(a, b)).toBe(0.48);
  });

  it('returns balanced pairs with correct scores', () => {
    const cases: [string, string, number][] = [
      ['balanced', 'grinder', 0.44],
      ['balanced', 'deep_diver', 0.44],
      ['balanced', 'specialist', 0.44],
      ['balanced', 'balanced', 0.4],
    ];
    for (const [s1, s2, expected] of cases) {
      const a = makeProfile({ userId: 'a', strengths: [], weaknesses: [], overallScore: 0.5, style: s1 });
      const b = makeProfile({ userId: 'b', strengths: [], weaknesses: [], overallScore: 0.5, style: s2 });
      expect(calcCompatibility(a, b)).toBe(expected);
    }
  });

  it('uses default style score 0.5 for unknown style pairs', () => {
    const a = makeProfile({ userId: 'a', strengths: [], weaknesses: [], overallScore: 0.5, style: 'unknown_x' });
    const b = makeProfile({ userId: 'b', strengths: [], weaknesses: [], overallScore: 0.5, style: 'unknown_y' });
    // default 0.5 → total = 0.3 + 0.5*0.2 = 0.4
    expect(calcCompatibility(a, b)).toBe(0.4);
  });

  it('is order-independent (commutative)', () => {
    const a = makeProfile({ userId: 'a', strengths: ['dp'], weaknesses: ['math'], overallScore: 0.6, style: 'grinder' });
    const b = makeProfile({ userId: 'b', strengths: ['graph'], weaknesses: ['dp'], overallScore: 0.8, style: 'deep_diver' });
    expect(calcCompatibility(a, b)).toBe(calcCompatibility(b, a));
  });

  // ── Integration / boundary ──

  it('stays within [0,1] for extreme score differences', () => {
    const a = makeProfile({ userId: 'a', strengths: [], weaknesses: [], overallScore: 0, style: null });
    const b = makeProfile({ userId: 'b', strengths: [], weaknesses: [], overallScore: 1, style: null });
    const result = calcCompatibility(a, b);
    expect(result).toBeGreaterThanOrEqual(0);
    expect(result).toBeLessThanOrEqual(1);
  });
});

// ─── 2. calcTeamScore ───────────────────────────────────────────────────────

describe('calcTeamScore', () => {
  const u0 = makeProfile({ userId: 'u0', strengths: ['dp', 'graph', 'math'], weaknesses: [], overallScore: 0.6, style: 'grinder' });
  const u1 = makeProfile({ userId: 'u1', strengths: ['geometry', 'string'], weaknesses: [], overallScore: 0.5, style: 'deep_diver' });
  const u2 = makeProfile({ userId: 'u2', strengths: ['ad-hoc', 'greedy'], weaknesses: [], overallScore: 0.7, style: 'specialist' });

  it('returns a score in 0~1 range', () => {
    const score = calcTeamScore([u0, u1, u2]);
    expect(score).toBeGreaterThanOrEqual(0);
    expect(score).toBeLessThanOrEqual(1);
  });

  it('returns fixed to 3 decimal places', () => {
    const score = calcTeamScore([u0, u1, u2]);
    const decimals = String(score).split('.')[1]?.length ?? 0;
    expect(decimals).toBeLessThanOrEqual(3);
  });

  it('throws when given fewer than 3 users', () => {
    expect(() => calcTeamScore([u0, u1])).toThrow('exactly 3');
  });

  it('throws when given more than 3 users', () => {
    expect(() => calcTeamScore([u0, u1, u2, u0])).toThrow('exactly 3');
  });

  it('covers union of strengths / 10 component', () => {
    // 3 users with disjoint strengths: dp,graph,math + geometry,string + ad-hoc,greedy = 7
    // coverage = 7/10 = 0.7 * 0.3 = 0.21 contribution
    const score = calcTeamScore([u0, u1, u2]);
    const pairScores = [
      calcCompatibility(u0, u1),
      calcCompatibility(u0, u2),
      calcCompatibility(u1, u2),
    ];
    const avgPair = pairScores.reduce((s, v) => s + v, 0) / 3;
    const expected = Math.round((avgPair * 0.7 + 0.7 * 0.3) * 1000) / 1000;
    expect(score).toBe(expected);
  });

  it('caps coverage ratio at 1.0 when strengths union > 10', () => {
    const big = makeProfile({
      userId: 'big',
      strengths: ['a', 'b', 'c', 'd', 'e', 'f', 'g', 'h', 'i', 'j', 'k', 'l'],
      weaknesses: [],
      overallScore: 0.5,
      style: null,
    });
    const score = calcTeamScore([big, big, big]);
    // coverage: 12 strengths, 12/10 = 1.2 → capped at 1.0
    const pairBase = calcCompatibility(big, big);
    const expected = Math.round((pairBase * 0.7 + 1.0 * 0.3) * 1000) / 1000;
    expect(score).toBe(expected);
  });

  it('handles users with empty strengths', () => {
    const e0 = makeProfile({ userId: 'e0', strengths: [], weaknesses: [], overallScore: 0.5, style: null });
    const e1 = makeProfile({ userId: 'e1', strengths: [], weaknesses: [], overallScore: 0.5, style: null });
    const e2 = makeProfile({ userId: 'e2', strengths: [], weaknesses: [], overallScore: 0.5, style: null });
    const score = calcTeamScore([e0, e1, e2]);
    expect(score).toBeGreaterThanOrEqual(0);
    expect(score).toBeLessThanOrEqual(1);
  });
});

// ─── 3. recommendTeammates ──────────────────────────────────────────────────

describe('recommendTeammates', () => {
  const user = makeProfile({
    userId: 'self',
    strengths: ['dp', 'graph'],
    weaknesses: ['string', 'math'],
    overallScore: 0.6,
    style: 'grinder',
  });

  const candidates: ProfileSnapshot[] = [
    makeProfile({ userId: 'c1', strengths: ['string', 'geometry'], weaknesses: ['dp'], overallScore: 0.55, style: 'deep_diver' }),
    makeProfile({ userId: 'c2', strengths: ['math', 'ad-hoc'], weaknesses: ['graph'], overallScore: 0.65, style: 'specialist' }),
    makeProfile({ userId: 'c3', strengths: ['greedy', 'brute'], weaknesses: ['dp'], overallScore: 0.5, style: 'balanced' }),
    makeProfile({ userId: 'c4', strengths: ['dp', 'number-theory'], weaknesses: ['sorting'], overallScore: 0.7, style: 'grinder' }),
    makeProfile({ userId: 'c5', strengths: ['geometry', 'combinatorics'], weaknesses: ['graph'], overallScore: 0.45, style: 'deep_diver' }),
  ];

  it('returns up to topK results', () => {
    const results = recommendTeammates(user, candidates, 2);
    expect(results.length).toBeLessThanOrEqual(2);
    expect(results.length).toBeGreaterThan(0);
  });

  it('returns fewer results when candidates are insufficient', () => {
    const fewResults = recommendTeammates(user, [candidates[0], candidates[1]], 5);
    // C(2,2) = 1 trio only
    expect(fewResults.length).toBe(1);
  });

  it('returns empty array when fewer than 2 eligible candidates', () => {
    const oneResult = recommendTeammates(user, [candidates[0]], 5);
    expect(oneResult).toEqual([]);
  });

  it('excludes self from candidates even if present', () => {
    const withSelf = [...candidates, user];
    const results = recommendTeammates(user, withSelf, 5);
    for (const r of results) {
      expect(r.teammates[0].userId).not.toBe(user.userId);
      expect(r.teammates[1].userId).not.toBe(user.userId);
    }
  });

  it('excludes users in excludeUserIds', () => {
    const results = recommendTeammates(user, candidates, 5, ['c1']);
    for (const r of results) {
      expect(r.teammates[0].userId).not.toBe('c1');
      expect(r.teammates[1].userId).not.toBe('c1');
    }
  });

  it('results are sorted by teamScore descending', () => {
    const results = recommendTeammates(user, candidates, 5);
    for (let i = 1; i < results.length; i++) {
      expect(results[i].teamScore).toBeLessThanOrEqual(results[i - 1].teamScore);
    }
  });

  it('result shape has all required fields', () => {
    const results = recommendTeammates(user, candidates, 3);
    expect(results.length).toBeGreaterThan(0);
    const r = results[0];
    expect(r).toHaveProperty('teammates');
    expect(r).toHaveProperty('teamScore');
    expect(r).toHaveProperty('pairScores');
    expect(r).toHaveProperty('complementDetails');
    expect(r).toHaveProperty('skillCoverageRatio');
    expect(r.teammates).toHaveLength(2);
    expect(r.pairScores).toHaveLength(3);
    expect(r.complementDetails).toHaveProperty('skillComplement');
    expect(r.complementDetails).toHaveProperty('levelProximity');
    expect(r.complementDetails).toHaveProperty('styleDiversity');
    expect(r.skillCoverageRatio).toBeGreaterThanOrEqual(0);
    expect(r.skillCoverageRatio).toBeLessThanOrEqual(1);
  });

  it('pairScores are in [0,1] and fixed to 3 decimals', () => {
    const results = recommendTeammates(user, candidates, 5);
    for (const r of results) {
      for (const ps of r.pairScores) {
        expect(ps).toBeGreaterThanOrEqual(0);
        expect(ps).toBeLessThanOrEqual(1);
        const decimals = String(ps).split('.')[1]?.length ?? 0;
        expect(decimals).toBeLessThanOrEqual(3);
      }
    }
  });

  it('complementDetails are in [0,1] and fixed to 3 decimals', () => {
    const results = recommendTeammates(user, candidates, 5);
    for (const r of results) {
      const { skillComplement, levelProximity, styleDiversity } = r.complementDetails;
      for (const v of [skillComplement, levelProximity, styleDiversity]) {
        expect(v).toBeGreaterThanOrEqual(0);
        expect(v).toBeLessThanOrEqual(1);
        const decimals = String(v).split('.')[1]?.length ?? 0;
        expect(decimals).toBeLessThanOrEqual(3);
      }
    }
  });

  it('defaults topK to 5', () => {
    const manyCandidates = Array.from({ length: 30 }, (_, i) =>
      makeProfile({
        userId: `gc${i}`,
        strengths: [`tag_${i % 10}`],
        weaknesses: [`tag_${(i + 5) % 10}`],
        overallScore: 0.3 + (i % 5) * 0.1,
        style: ['grinder', 'deep_diver', 'specialist', 'balanced'][i % 4],
      }),
    );
    const results = recommendTeammates(user, manyCandidates);
    expect(results.length).toBeLessThanOrEqual(5);
  });

  it('handles empty candidates array', () => {
    const results = recommendTeammates(user, [], 5);
    expect(results).toEqual([]);
  });
});
