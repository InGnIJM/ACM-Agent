import { PrismaClient } from '@prisma/client';

const p = new PrismaClient();

async function main() {
  const lc = await p.problem.findFirst({
    where: { sourcePlatform: 'leetcode', sourceId: '8' },
    select: { rawDetail: true, fullContent: true, title: true },
  });
  const rd = (lc?.rawDetail || {}) as any;
  const html: string = rd?.content || '';

  console.log('Title:', lc?.title);
  console.log('Has content HTML:', !!html);

  // Check if content has pre blocks with Chinese labels
  console.log('Has <pre> with 输入:', /<pre>[\s\S]*?输入/.test(html));
  console.log('Has <pre> with 输出:', /<pre>[\s\S]*?输出/.test(html));

  // Find all <pre> blocks
  const pres = html.match(/<pre>[\s\S]*?<\/pre>/gi) || [];
  console.log('Total <pre> blocks:', pres.length);
  for (let i = 0; i < Math.min(pres.length, 3); i++) {
    console.log(`\n<pre> #${i + 1} (first 500 chars):`);
    console.log(pres[i].substring(0, 500));
  }

  // Check fullContent [样例] section
  const fc = lc?.fullContent || '';
  const idx = fc.indexOf('[样例]');
  if (idx >= 0) {
    console.log('\n=== [样例] section (first 2000 chars) ===');
    console.log(fc.substring(idx, idx + 2000));
  } else {
    console.log('\nNo [样例] section in fullContent!');
  }

  // Check if there's a [描述] section with examples
  const descIdx = fc.indexOf('[描述]');
  if (descIdx >= 0) {
    console.log('\n=== [描述] section start (first 500 chars) ===');
    console.log(fc.substring(descIdx, descIdx + 500));
  }

  await p.$disconnect();
}

main();
