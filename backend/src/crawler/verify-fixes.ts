/** Quick verification of the 4 fixed problems */
import { PrismaClient } from '@prisma/client';

const p = new PrismaClient();

async function verify(platform: string, sourceId: string, checks: string[]) {
  const problem = await p.problem.findUnique({
    where: { sourcePlatform_sourceId: { sourcePlatform: platform as any, sourceId } },
    select: { title: true, fullContent: true },
  });
  console.log(`\n=== ${platform}/${sourceId}: ${problem?.title || 'NOT FOUND'} ===`);
  const fc = problem?.fullContent || '';
  if (!fc) { console.log('  EMPTY fullContent!'); return; }

  for (const label of checks) {
    if (fc.includes(label)) {
      console.log(`  PASS: contains "${label}"`);
    } else {
      console.log(`  FAIL: missing "${label}"`);
    }
  }

  // LeetCode: count samples
  if (platform === 'leetcode') {
    const idx = fc.indexOf('[样例]');
    if (idx >= 0) {
      const section = fc.substring(idx);
      const count = (section.match(/输入 #/g) || []).length;
      console.log(`  Sample count: ${count} (expected 5)`);
    }
  }

  // CF: check for char spacing artifacts
  if (platform === 'codeforces') {
    const spaced = fc.match(/\b([A-Z]) ([a-z])/g);
    if (spaced && spaced.length > 5) {
      console.log(`  WARN: ${spaced.length} single-char spacing artifacts found`);
    } else {
      console.log(`  PASS: no excessive single-char spacing`);
    }
  }

  // NowCoder: check for smart quote artifacts
  if (platform === 'nowcoder') {
    const sq = fc.match(/['‘’]/g);
    console.log(`  Smart-quote count: ${sq ? sq.length : 0}`);
  }
}

async function main() {
  await verify('leetcode', '8', ['输入 #1', '输出 #1', '输入 #5', '输出 #5']);
  await verify('codeforces', '2236F2', ['^{\\ast}', 'p_1 \\cdot p_2']);
  await verify('nowcoder', '317391', ['[输入]', '[输出]', '[样例]']);
  await verify('atcoder', '1202Contest_a', ['输入 #1', '输出 #1']);
  await p.$disconnect();
}

main();
