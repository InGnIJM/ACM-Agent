import { PrismaClient } from '@prisma/client';
const p = new PrismaClient();

async function check(id: string, label: string, tests: Array<{desc: string; fn: (fc: string) => boolean}>) {
  const prob = await p.problem.findUnique({ where: { id }, select: { title: true, fullContent: true } });
  const fc = prob?.fullContent || '';
  console.log(`\n=== ${label}: ${prob?.title || 'NOT FOUND'} ===`);
  for (const t of tests) {
    const ok = t.fn(fc);
    console.log(`  ${ok ? '✅' : '❌'} ${t.desc}`);
  }
}

async function main() {
  // 1. LeetCode: description before samples, no spurious input/output sections
  await check('db02abdc-8db1-4e64-99e7-6a4ef3a7fa59', 'LeetCode 8', [
    { desc: '[描述] before [样例]', fn: fc => fc.indexOf('[描述]') < fc.indexOf('[样例]') },
    { desc: 'NO [输入] section', fn: fc => !fc.includes('[输入]') },
    { desc: 'NO [输出] section', fn: fc => !fc.includes('[输出]') },
    { desc: '5 samples (输入 #5)', fn: fc => fc.includes('输入 #5') },
    { desc: 'NO orphaned "示例 1：" labels', fn: fc => {
      const descStart = fc.indexOf('[描述]');
      const sampleStart = fc.indexOf('[样例]');
      const descSection = fc.substring(descStart, sampleStart > descStart ? sampleStart : undefined);
      return !descSection.includes('示例 1：') && !descSection.includes('示例 2：');
    }},
  ]);

  // 2. AtCoder: code block in input_format
  await check('3c4702ce-9254-4e8d-9060-6532df55b63d', 'AtCoder 1202Contest_a', [
    { desc: 'input has code fence ```', fn: fc => {
      const inpIdx = fc.indexOf('[输入]');
      const nextIdx = fc.indexOf('[输出]');
      const inpSection = fc.substring(inpIdx, nextIdx);
      return inpSection.includes('```');
    }},
    { desc: 'Samples present', fn: fc => fc.includes('输入 #1') && fc.includes('输出 #1') },
  ]);

  // 3. NowCoder: samples present
  await check('27d809d0-f814-4264-9cbc-3a560c79a933', 'NowCoder 317391', [
    { desc: 'Has [输入] section', fn: fc => fc.includes('[输入]') },
    { desc: 'Has [输出] section', fn: fc => fc.includes('[输出]') },
    { desc: 'Has [样例] section', fn: fc => fc.includes('[样例]') },
    { desc: 'NO triple-quote artifacts', fn: fc => !fc.includes("'''") },
    { desc: 'Sample input is multi-line', fn: fc => {
      const sIdx = fc.indexOf('[样例]');
      if (sIdx < 0) return false;
      const s = fc.substring(sIdx);
      const m = s.match(/输入 #1\n```\n([\s\S]*?)```/);
      if (!m) return false;
      return (m[1].match(/\n/g) || []).length >= 2; // multi-line input
    }},
  ]);

  await p.$disconnect();
}
main();
