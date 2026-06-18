import { PrismaClient } from '@prisma/client';
const p = new PrismaClient();

async function main() {
  const ac = await p.problem.findFirst({
    where: { sourcePlatform: 'atcoder', sourceId: '1202Contest_a' },
    select: { rawDetail: true, fullContent: true, title: true },
  });
  const rd = (ac?.rawDetail || {}) as any;
  console.log('Title:', ac?.title);
  console.log('Keys:', Object.keys(rd).join(', '));

  // Show input_format
  const inf = rd.input_format || '';
  console.log('\n=== input_format ===');
  console.log(inf.substring(0, 800));

  // Show samples
  const samples = rd.samples || [];
  console.log('\n=== samples ===');
  samples.forEach((s: any, i: number) => {
    console.log(`\nSample ${i + 1}:`);
    console.log('  Input:', (s[0] || '').substring(0, 200));
    console.log('  Output:', (s[1] || '').substring(0, 200));
  });

  // Show fullContent
  const fc = ac?.fullContent || '';
  const idx = fc.indexOf('[输入]');
  if (idx >= 0) console.log('\n=== fullContent [输入] section ===');
  console.log(fc.substring(idx, idx + 600));

  await p.$disconnect();
}
main();
