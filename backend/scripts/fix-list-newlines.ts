/**
 * Fix corrupted fullContent where list-item newlines were lost.
 *
 * Root cause: _cf_extract() in python/crawlers/codeforces.py had a merge-orphan
 * logic that incorrectly merged standalone "-" lines (from <li> conversion) into
 * the preceding line, destroying list structure.
 *
 * Fix: restore "\n" before "- " markers that are directly attached to preceding
 * text without a newline separator.
 *
 * Usage:
 *   npx ts-node scripts/fix-list-newlines.ts <problem-uuid>    # fix one
 *   npx ts-node scripts/fix-list-newlines.ts --all             # fix all CF
 *   npx ts-node scripts/fix-list-newlines.ts --scan            # scan only
 */

import { PrismaClient } from '@prisma/client';

const prisma = new PrismaClient();

const fixListMarkers = (text: string): string => {
  if (!text) return text;
  // Insert \n before "- " when preceded by a letter, digit, colon, or semicolon.
  //   "such that:- each"   → "such that:\n- each"
  //   "distinct;- $p_{2}"  → "distinct;\n- $p_{2}"
  // Restricted to [a-z0-9:;] to avoid breaking LaTeX `$- x$` patterns.
  return text.replace(/([a-z0-9:;])- /gi, '$1\n- ');
};

const isCorrupted = (text: string): boolean => {
  return /[a-z0-9]:- /i.test(text) || /[a-z];- /i.test(text);
};

async function scanAll() {
  const problems = await prisma.problem.findMany({
    where: { sourcePlatform: 'codeforces', deletedAt: null },
    select: { id: true, sourceId: true, title: true, fullContent: true, rawDetail: true },
  });
  console.log(`Total CF problems: ${problems.length}`);

  const corrupted = problems.filter(p => isCorrupted(p.fullContent ?? ''));
  console.log(`Corrupted: ${corrupted.length}`);
  for (const c of corrupted) {
    console.log(`  ${c.sourceId.padEnd(12)} ${(c.title || '').slice(0, 40)}`);
  }
  return corrupted;
}

async function fixAll() {
  const problems = await prisma.problem.findMany({
    where: { sourcePlatform: 'codeforces', deletedAt: null },
    select: { id: true, sourceId: true, title: true, fullContent: true, rawDetail: true },
  });

  const corrupted = problems.filter(p => isCorrupted(p.fullContent ?? ''));
  if (corrupted.length === 0) {
    console.log('No corrupted problems found.');
    return;
  }

  console.log(`Fixing ${corrupted.length} corrupted problems...`);
  let fixed = 0;
  for (const problem of corrupted) {
    try {
      const fixedFC = fixListMarkers(problem.fullContent ?? '');
      if (fixedFC === problem.fullContent) continue;

      const rawDetail = problem.rawDetail as Record<string, unknown> | null;
      let rawDetailChanged = false;
      if (rawDetail && typeof rawDetail.description === 'string') {
        const fixedDesc = fixListMarkers(rawDetail.description);
        if (fixedDesc !== rawDetail.description) {
          rawDetail.description = fixedDesc;
          rawDetailChanged = true;
        }
      }

      await prisma.problem.update({
        where: { id: problem.id },
        data: {
          fullContent: fixedFC,
          ...(rawDetailChanged ? { rawDetail: rawDetail as any } : {}),
        },
      });
      fixed++;
      console.log(`  ✅ ${problem.sourceId}: ${(problem.title || '').slice(0, 40)}`);
    } catch (err: any) {
      console.error(`  ❌ ${problem.sourceId}: ${err?.message || err}`);
    }
  }
  console.log(`\nFixed: ${fixed}/${corrupted.length}`);
}

async function fixOne(problemId: string) {
  const problem = await prisma.problem.findUnique({
    where: { id: problemId },
    select: { id: true, title: true, sourceId: true, fullContent: true, rawDetail: true },
  });
  if (!problem) {
    console.error(`Problem not found: ${problemId}`);
    process.exit(1);
  }

  console.log(`Fixing: ${problem.title} (${problem.sourceId})`);
  const fixedFC = fixListMarkers(problem.fullContent ?? '');

  if (fixedFC === (problem.fullContent ?? '')) {
    console.log('  No list-marker corruption detected.');
    return;
  }

  const rawDetail = problem.rawDetail as Record<string, unknown> | null;
  let rawDetailChanged = false;
  if (rawDetail && typeof rawDetail.description === 'string') {
    const fixedDesc = fixListMarkers(rawDetail.description);
    if (fixedDesc !== rawDetail.description) {
      rawDetail.description = fixedDesc;
      rawDetailChanged = true;
    }
  }

  await prisma.problem.update({
    where: { id: problemId },
    data: {
      fullContent: fixedFC,
      ...(rawDetailChanged ? { rawDetail: rawDetail as any } : {}),
    },
  });
  console.log('  ✅ Updated.');
}

async function main() {
  const arg = process.argv[2];

  if (arg === '--all') {
    await fixAll();
  } else if (arg === '--scan') {
    await scanAll();
  } else if (arg) {
    await fixOne(arg);
  } else {
    console.error('Usage: npx ts-node scripts/fix-list-newlines.ts <problem-uuid> | --all | --scan');
    process.exit(1);
  }
}

main()
  .catch((err) => {
    console.error(err);
    process.exit(1);
  })
  .finally(() => prisma.$disconnect());
