/**
 * ONE-OFF rebuild script: recompute `full_content` for ALL atcoder problems
 * from their stored `raw_detail` using the FIXED shared pure module
 * `backend/src/crawler/fullcontent.util.ts` (buildFullContent).
 *
 * Why: the backend data-loss bug (MathJax triplication cleaner deleting
 * AtCoder constraint lines like "$1 \leq H \leq 20$") was fixed by gating
 * the cleaner off for atcoder/luogu platforms inside the shared util.
 * Existing DB rows still hold the OLD, truncated full_content.  This
 * script rebuilds them IN PLACE from raw_detail — NO re-crawl.
 *
 * Usage:
 *   cd backend && npx tsx scripts/rebuild-atcoder-fullcontent.ts            # write
 *   cd backend && npx tsx scripts/rebuild-atcoder-fullcontent.ts --dry-run  # preview only
 *
 * Scope: every row in problems WHERE source_platform='atcoder'.
 * NOTE: 1202Contest_j is currently soft-deleted (deleted_at IS NOT NULL)
 * but is intentionally INCLUDED — the task enumerates all 3 rows and
 * expects _j's rebuilt content to correctly OMIT [数据范围] (its raw_detail
 * has no constraints key).  Rebuilding a soft-deleted row's denormalized
 * full_content is harmless and keeps it correct if the row is restored.
 * Idempotent — safe to re-run.
 */
import { PrismaClient } from '@prisma/client';
import { buildFullContent } from '../src/crawler/fullcontent.util';

const prisma = new PrismaClient();

const DRY_RUN = process.argv.includes('--dry-run');

const SECTION_MARKERS = ['[描述]', '[输入]', '[输出]', '[数据范围]', '[样例]'];

function markersPresent(text: string): string[] {
  return SECTION_MARKERS.filter(m => text.includes(m));
}

async function main(): Promise<void> {
  const rows = await prisma.problem.findMany({
    where: { sourcePlatform: 'atcoder' },
    select: { id: true, sourceId: true, rawDetail: true, fullContent: true },
    orderBy: { sourceId: 'asc' },
  });

  console.log(`Found ${rows.length} atcoder problem(s). mode=${DRY_RUN ? 'DRY-RUN' : 'WRITE'}`);

  let updated = 0;
  for (const row of rows) {
    const before = row.fullContent || '';
    const newContent = buildFullContent('atcoder', row.rawDetail as any);

    console.log(`\n──────── ${row.sourceId} (${row.id}) ────────`);
    console.log(`  BEFORE len=${before.length}  markers=${markersPresent(before).join(',') || '(none)'}`);
    console.log(`  AFTER  len=${newContent.length}  markers=${markersPresent(newContent).join(',') || '(none)'}`);

    if (DRY_RUN) {
      // Surface specific sections for eyeballing without writing anything.
      if (/1202Contest_b$/i.test(row.sourceId)) {
        const drIdx = newContent.indexOf('[数据范围]');
        const outIdx = newContent.indexOf('[输出]');
        if (drIdx >= 0) {
          const end = outIdx > drIdx ? outIdx : newContent.length;
          console.log(`\n  >> [数据范围] section for ${row.sourceId}:\n${newContent.slice(drIdx, end).trim()}`);
        }
        if (outIdx >= 0) {
          console.log(`\n  >> [输出] section for ${row.sourceId}:\n${newContent.slice(outIdx).trim()}`);
        }
      }
      // For _j: print the whole rebuilt content so the absence of [数据范围]
      // can be verified (its raw_detail has no constraints key — honest omission).
      if (/1202Contest_j$/i.test(row.sourceId)) {
        console.log(`\n  >> FULL rebuilt content for ${row.sourceId}:\n----------\n${newContent}\n----------`);
      }
      continue;
    }

    if (newContent === before) {
      console.log(`  (no change — skipping UPDATE)`);
      continue;
    }

    await prisma.problem.update({
      where: { id: row.id },
      data: { fullContent: newContent, updatedAt: new Date() },
    });
    updated++;
    console.log(`  [OK] updated`);
  }

  console.log(`\nDone. rows processed=${rows.length} rows updated=${updated}`);
}

main()
  .catch(async (e) => {
    console.error('Fatal:', e);
    await prisma.$disconnect();
    process.exit(1);
  })
  .finally(() => prisma.$disconnect());
