/**
 * Clean up garbage/duplicate CF solutions.
 *
 * Removes:
 * 1. Russian spam from blog/entry/{contest_id} fallback (contains Cyrillic)
 * 2. Exact duplicate solutions (same problem + same content)
 */

import { PrismaClient } from '@prisma/client';

const prisma = new PrismaClient();

async function main() {
  // ── 1. Remove solutions containing Cyrillic (Russian spam from wrong blog) ──
  const cyrillic = await prisma.problemSolution.findMany({
    where: {
      content: { contains: 'Ч' },  // Cyrillic 'Che' — unique to Russian
      problem: { sourcePlatform: 'codeforces' },
    },
    select: { id: true },
  });
  if (cyrillic.length > 0) {
    await prisma.problemSolution.deleteMany({
      where: { id: { in: cyrillic.map(s => s.id) } },
    });
    console.log(`Removed ${cyrillic.length} Russian-spam solutions`);
  } else {
    console.log('No Russian-spam solutions found');
  }

  // ── 2. Remove exact duplicates (same problem + same content) ──
  const dups = await prisma.$queryRawUnsafe<Array<{problem_id: string, content_hash: string, cnt: number}>>(`
    SELECT problem_id, md5(content) as content_hash, count(*) as cnt
    FROM problem_solutions
    WHERE problem_id IN (
      SELECT id FROM problems WHERE source_platform = 'codeforces' AND deleted_at IS NULL
    )
    GROUP BY problem_id, md5(content)
    HAVING count(*) > 1
  `);

  let dupRemoved = 0;
  for (const dup of dups) {
    // Keep the first (oldest) one, delete the rest
    const ids = await prisma.problemSolution.findMany({
      where: { problemId: dup.problem_id },
      select: { id: true, content: true },
      orderBy: { createdAt: 'asc' },
    });
    const seen = new Set<string>();
    const toDelete: string[] = [];
    for (const s of ids) {
      const hash = s.content.slice(0, 100); // Simple fingerprint
      if (seen.has(hash)) {
        toDelete.push(s.id);
      } else {
        seen.add(hash);
      }
    }
    if (toDelete.length > 0) {
      await prisma.problemSolution.deleteMany({ where: { id: { in: toDelete } } });
      dupRemoved += toDelete.length;
    }
  }
  console.log(`Removed ${dupRemoved} duplicate solutions`);

  console.log('Done.');
}

main()
  .catch((e) => { console.error(e); process.exit(1); })
  .finally(() => prisma.$disconnect());
