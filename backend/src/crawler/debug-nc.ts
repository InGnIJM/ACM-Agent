import { PrismaClient } from '@prisma/client';
const p = new PrismaClient();

async function main() {
  const nc = await p.problem.findFirst({
    where: { sourcePlatform: 'nowcoder', sourceId: '317391' },
    select: { rawDetail: true, fullContent: true, title: true },
  });
  const rd = (nc?.rawDetail || {}) as any;
  console.log('Title:', nc?.title);
  console.log('Keys in rawDetail:', Object.keys(rd).join(', '));

  // Check key sections
  console.log('Has description:', !!rd.description);
  console.log('Has input_format:', !!rd.input_format);
  console.log('Has output_format:', !!rd.output_format);
  console.log('Has samples:', !!rd.samples);
  if (rd.samples) console.log('Sample count:', rd.samples.length);

  // Print description first 500 chars
  if (rd.description) {
    console.log('\n--- description (first 800 chars) ---');
    console.log(rd.description.substring(0, 800));
  }
  if (rd.input_format) {
    console.log('\n--- input_format ---');
    console.log(rd.input_format.substring(0, 500));
  }
  if (rd.output_format) {
    console.log('\n--- output_format ---');
    console.log(rd.output_format.substring(0, 500));
  }

  // Print fullContent
  const fc = nc?.fullContent || '';
  console.log('\n=== fullContent (first 3000 chars) ===');
  console.log(fc.substring(0, 3000));

  await p.$disconnect();
}

main();
