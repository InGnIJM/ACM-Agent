import { PrismaClient } from '@prisma/client';
const p = new PrismaClient();

async function main() {
  const cf = await p.problem.findFirst({
    where: { sourcePlatform: 'codeforces', sourceId: { startsWith: '2236' } },
    select: { sourceId: true, title: true, rawDetail: true, fullContent: true },
  });
  if (!cf) { console.log('NOT FOUND'); await p.$disconnect(); return; }

  const rd = cf.rawDetail as any;
  console.log('SourceId:', cf.sourceId);
  console.log('Title:', cf.title);
  console.log('output_format:', (rd.output_format || '').substring(0, 200));
  console.log('samples count:', rd.samples?.length);
  if (rd.samples) {
    rd.samples.forEach((s: any, i: number) => {
      console.log(`\nSample ${i + 1}:`);
      console.log('  Input:', JSON.stringify((s[0] || '').substring(0, 200)));
      console.log('  Output:', JSON.stringify((s[1] || '').substring(0, 200)));
    });
  }

  // Check fullContent [样例] section
  const fc = cf.fullContent || '';
  const idx = fc.indexOf('[样例]');
  if (idx >= 0) {
    console.log('\n=== fullContent [样例] (first 1500 chars) ===');
    console.log(fc.substring(idx, idx + 1500));
  }
  const outIdx = fc.indexOf('[输出]');
  if (outIdx >= 0) {
    console.log('\n=== fullContent [输出] ===');
    console.log(fc.substring(outIdx, outIdx + 300));
  }

  await p.$disconnect();
}
main();
