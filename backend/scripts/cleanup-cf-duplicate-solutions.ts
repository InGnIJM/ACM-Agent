/**
 * 清除 CF 题解重复数据：保留每题最新的 1 条，删除其余。
 *
 * 用法：
 *   npx ts-node backend/scripts/cleanup-cf-duplicate-solutions.ts
 */
import { PrismaClient } from '@prisma/client';

const prisma = new PrismaClient();

async function main(): Promise<void> {
  // 1. 找出有重复题解的 CF 题目
  const dupes = await prisma.$queryRaw<Array<{ problem_id: string; cnt: bigint }>>`
    SELECT ps."problem_id"::text, COUNT(*) as cnt
    FROM "problem_solutions" ps
    JOIN "problems" p ON p.id = ps."problem_id"
    WHERE p."source_platform" = 'codeforces'::"Platform"
      AND p."deleted_at" IS NULL
    GROUP BY ps."problem_id"
    HAVING COUNT(*) > 1
  `;

  console.log(`Found ${dupes.length} CF problems with duplicate solutions`);

  if (dupes.length === 0) {
    console.log('Nothing to clean up.');
    await prisma.$disconnect();
    return;
  }

  let totalDeleted = 0;

  for (const row of dupes) {
    // 2. 对每个问题，找所有题解，按创建时间排序
    const solutions = await prisma.problemSolution.findMany({
      where: { problemId: row.problem_id as any },
      orderBy: { createdAt: 'desc' },
      select: {
        id: true,
        solutionIndex: true,
        content: true,
        createdAt: true,
      },
    });

    if (solutions.length <= 1) continue;

    // 3. 保留第一条（最新的），删除其余的
    const [keep, ...remove] = solutions;

    // 同时查一下题目信息用于日志
    const problem = await prisma.problem.findUnique({
      where: { id: row.problem_id as any },
      select: { sourceId: true, title: true },
    });

    for (const sol of remove) {
      await prisma.problemSolution.delete({
        where: { id: sol.id },
      });
      totalDeleted++;
    }

    console.log(
      `  ${problem?.sourceId || '?'} (${problem?.title?.slice(0, 40) || '?'}): ` +
      `kept solutionIndex=${keep.solutionIndex}, ` +
      `deleted ${remove.length} (indexes: ${remove.map(r => r.solutionIndex).join(', ')})`,
    );
  }

  console.log(`\nDone: deleted ${totalDeleted} duplicate solutions`);
  await prisma.$disconnect();
}

main().catch(async (e) => {
  console.error('Fatal:', e);
  await prisma.$disconnect();
  process.exit(1);
});
