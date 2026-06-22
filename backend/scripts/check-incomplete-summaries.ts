import { PrismaClient } from '@prisma/client';
import * as dotenv from 'dotenv';
import * as path from 'path';

dotenv.config({ path: path.resolve(__dirname, '..', '.env') });

const prisma = new PrismaClient();

async function main() {
  // 1. 统计总数
  const total = await prisma.problem.count({ where: { deletedAt: null } });
  console.log('题目总数:', total);

  // 2. NULL / 空
  const nullResult: any[] = await prisma.$queryRawUnsafe(`
    SELECT COUNT(*)::int AS cnt FROM problems
    WHERE deleted_at IS NULL AND (solution_summary IS NULL OR solution_summary = '')
  `);
  console.log('NULL/空摘要:', nullResult[0]?.cnt ?? '?');

  // 3. 长度分布
  const lenStats: any[] = await prisma.$queryRawUnsafe(`
    SELECT
      COUNT(*)::int AS total_with_summary,
      MIN(LENGTH(solution_summary))::int AS min_len,
      MAX(LENGTH(solution_summary))::int AS max_len,
      ROUND(AVG(LENGTH(solution_summary)))::int AS avg_len
    FROM problems
    WHERE deleted_at IS NULL AND solution_summary IS NOT NULL AND solution_summary != ''
  `);
  console.log('有摘要题目长度分布:', JSON.stringify(lenStats[0]));

  // 4. 按 batch 脚本正则检查: 【核心考点】+【推荐解法】+【易错点】+ 完整结尾
  const batchFormat: any[] = await prisma.$queryRawUnsafe(`
    SELECT
      COUNT(*)::int AS total,
      COUNT(*) FILTER (WHERE solution_summary ~ '【核心考点】')::int AS has_kd,
      COUNT(*) FILTER (WHERE solution_summary ~ '【推荐解法】')::int AS has_approach,
      COUNT(*) FILTER (WHERE solution_summary ~ '【易错点】')::int AS has_pitfall,
      COUNT(*) FILTER (WHERE
        solution_summary ~ '【核心考点】'
        AND solution_summary ~ '【推荐解法】'
        AND solution_summary ~ '【易错点】'
        AND solution_summary ~ '[。.!！?？)）]\\s*$'
      )::int AS complete_batch_format
    FROM problems
    WHERE deleted_at IS NULL AND solution_summary IS NOT NULL AND solution_summary != ''
  `);
  console.log('\nBatch格式(【】) 检查:', JSON.stringify(batchFormat[0]));

  // 5. 按 English 格式检查 (summarizer.py): Summary:|Approach:|Key Points:|Pitfalls:
  const engFormat: any[] = await prisma.$queryRawUnsafe(`
    SELECT
      COUNT(*)::int AS total,
      COUNT(*) FILTER (WHERE solution_summary ~ '^Summary:')::int AS starts_with_summary,
      COUNT(*) FILTER (WHERE solution_summary ~ 'Approach:')::int AS has_approach,
      COUNT(*) FILTER (WHERE solution_summary ~ 'Key Points:')::int AS has_keypoints,
      COUNT(*) FILTER (WHERE solution_summary ~ 'Pitfalls:')::int AS has_pitfalls,
      COUNT(*) FILTER (WHERE
        solution_summary ~ '^Summary:'
        AND solution_summary ~ 'Approach:'
        AND solution_summary ~ 'Key Points:'
        AND solution_summary ~ 'Pitfalls:'
        AND solution_summary ~ '[。.!！?？)）]\\s*$'
      )::int AS complete_eng_format
    FROM problems
    WHERE deleted_at IS NULL AND solution_summary IS NOT NULL AND solution_summary != ''
  `);
  console.log('English格式(summarizer.py) 检查:', JSON.stringify(engFormat[0]));

  // 6. 两种格式都不完整（不完全摘要）
  const incomplete: any[] = await prisma.$queryRawUnsafe(`
    SELECT source_platform::text AS platform, source_id::text AS source_id, title,
           LENGTH(solution_summary) AS len,
           LEFT(solution_summary, 200) AS preview
    FROM problems
    WHERE deleted_at IS NULL
      AND solution_summary IS NOT NULL
      AND solution_summary != ''
      AND NOT (
        (solution_summary ~ '【核心考点】'
         AND solution_summary ~ '【推荐解法】'
         AND solution_summary ~ '【易错点】'
         AND solution_summary ~ '[。.!！?？)）]\\s*$')
        OR
        (solution_summary ~ '^Summary:'
         AND solution_summary ~ 'Approach:'
         AND solution_summary ~ 'Key Points:'
         AND solution_summary ~ 'Pitfalls:'
         AND solution_summary ~ '[。.!！?？)）]\\s*$')
      )
    ORDER BY len ASC
    LIMIT 30
  `);
  console.log('\n=== 不完全摘要 (两种格式都不完整, 前30条) ===');
  if (incomplete.length === 0) {
    console.log('  ✅ 无不完全摘要');
  } else {
    incomplete.forEach((r: any, i: number) => {
      console.log(`\n  [${i + 1}] [${r.platform}] ${r.source_id} "${r.title}"  len=${r.len}`);
      console.log(`      preview: ${r.preview}`);
    });
  }

  // 7. 完全无摘要
  const noSummary: any[] = await prisma.$queryRawUnsafe(`
    SELECT source_platform::text AS platform, source_id::text AS source_id, title
    FROM problems
    WHERE deleted_at IS NULL
      AND (solution_summary IS NULL OR solution_summary = '')
    ORDER BY created_at DESC
    LIMIT 30
  `);
  console.log('\n=== 完全无摘要 (前30条) ===');
  if (noSummary.length === 0) {
    console.log('  ✅ 无缺摘要题目');
  } else {
    noSummary.forEach((r: any, i: number) => {
      console.log(`  [${i + 1}] [${r.platform}] ${r.source_id} "${r.title}"`);
    });
  }

  await prisma.$disconnect();
}

main().catch(e => { console.error(e); process.exit(1); });
