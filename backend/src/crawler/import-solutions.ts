/**
 * Standalone script: import solution JSON files into the database.
 *
 * Reads saved solution JSON files from data/raw/{platform}/solutions/
 * and upserts them via Prisma into ProblemSolution records.
 *
 * Usage:
 *   npx ts-node src/crawler/import-solutions.ts [--platform codeforces|leetcode|nowcoder]
 *
 * Without --platform, imports all platforms.
 */

import { PrismaClient } from '@prisma/client';
import * as fs from 'fs';
import * as path from 'path';

const prisma = new PrismaClient();

const DATA_DIR = path.resolve(__dirname, '../../../python/data/raw');

interface SolutionRecord {
  author?: string;
  title?: string;
  content?: string;
  vote_count?: number;
  solution_index?: number;
  problem_id?: string;
  pid?: string;
  reply_count?: number;
  is_official?: boolean;
}

async function findProblem(
  platform: string,
  sourceIdHint: string,
  record: SolutionRecord,
): Promise<string | null> {
  // Strategy 1: use problem_id from record
  const recordPid = record.problem_id || record.pid;
  if (recordPid) {
    const p = await prisma.problem.findUnique({
      where: { sourcePlatform_sourceId: { sourcePlatform: platform as any, sourceId: String(recordPid) } },
      select: { id: true },
    });
    if (p) return p.id;
  }

  // Strategy 2: use sourceIdHint directly (matches CF numeric+letter, NC numeric IDs)
  if (sourceIdHint) {
    const p = await prisma.problem.findUnique({
      where: { sourcePlatform_sourceId: { sourcePlatform: platform as any, sourceId: sourceIdHint } },
      select: { id: true },
    });
    if (p) return p.id;
  }

  // Strategy 3: for LeetCode, sourceIdHint may be a titleSlug — look up via rawDetail
  if (platform === 'leetcode' && sourceIdHint) {
    const problems = await prisma.problem.findMany({
      where: { sourcePlatform: 'leetcode' },
      select: { id: true, sourceId: true, rawDetail: true },
    });
    for (const p of problems) {
      const detail = (p.rawDetail || {}) as any;
      const slug = detail.titleSlug || detail.slug || '';
      if (slug === sourceIdHint) {
        return p.id;
      }
    }
  }

  return null;
}

async function importPlatformSolutions(platform: string): Promise<number> {
  const solutionsDir = path.join(DATA_DIR, platform, 'solutions');
  if (!fs.existsSync(solutionsDir)) {
    console.log(`[${platform}] No solutions directory: ${solutionsDir}`);
    return 0;
  }

  const files = fs.readdirSync(solutionsDir).filter(
    (f) => f.endsWith('.json') && !f.startsWith('bulk_list_') && !f.startsWith('bulk_detail_progress_'),
  );
  if (files.length === 0) {
    console.log(`[${platform}] No solution files found`);
    return 0;
  }

  console.log(`[${platform}] Found ${files.length} solution files`);

  let totalImported = 0;

  for (const file of files) {
    const filePath = path.join(solutionsDir, file);
    try {
      const raw = JSON.parse(fs.readFileSync(filePath, 'utf-8'));
      const records: SolutionRecord[] = Array.isArray(raw) ? raw : [raw];

      // Extract sourceId from filename: {date}_{sourceId}.json
      const fileSourceId = file.replace(/^\d{4}-\d{2}-\d{2}_/, '').replace('.json', '');

      for (const sol of records) {
        const author = sol.author || '匿名';
        const content = sol.content || '';
        if (!content || content.length < 10) continue; // skip empty/noise content

        const problemId = await findProblem(platform, fileSourceId, sol);
        if (!problemId) {
          console.log(`  [${platform}] Skip: problem not found for hint="${fileSourceId}"`);
          continue;
        }

        const solutionIndex =
          sol.solution_index ??
          (sol.vote_count ? (sol.vote_count + Date.now() % 1000) : Date.now() % 10000);

        await prisma.problemSolution.upsert({
          where: {
            problemId_solutionIndex: {
              problemId,
              solutionIndex: Number(solutionIndex) % 100000,
            },
          },
          create: {
            problemId,
            solutionIndex: Number(solutionIndex) % 100000,
            content,
            author: String(author).slice(0, 100),
          },
          update: {
            content,
            author: String(author).slice(0, 100),
          },
        });

        totalImported++;
      }
    } catch (err: any) {
      console.warn(`  [${platform}] Failed to import ${file}: ${err?.message || err}`);
    }
  }

  console.log(`[${platform}] Imported ${totalImported} solutions`);
  return totalImported;
}

async function main(): Promise<void> {
  const args = process.argv.slice(2);
  const platformArg = args.find((a) => a.startsWith('--platform='));
  const targetPlatform = platformArg ? platformArg.split('=')[1] : null;

  await prisma.$connect();

  try {
    const platforms = targetPlatform ? [targetPlatform] : ['codeforces', 'leetcode', 'nowcoder'];
    const results: Record<string, number> = {};

    for (const platform of platforms) {
      const count = await importPlatformSolutions(platform);
      results[platform] = count;
    }

    console.log('\n=== IMPORT SUMMARY ===');
    let total = 0;
    for (const [plat, count] of Object.entries(results)) {
      console.log(`  ${plat}: ${count} solutions imported`);
      total += count;
    }
    console.log(`  TOTAL: ${total}`);
    console.log('======================');
  } finally {
    await prisma.$disconnect();
  }
}

main().catch((e) => {
  console.error('Import failed:', e);
  process.exit(1);
});
