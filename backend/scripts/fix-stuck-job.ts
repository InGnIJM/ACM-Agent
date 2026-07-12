import { PrismaClient } from '@prisma/client';

const p = new PrismaClient();
async function main() {
  // 标记所有卡住的 running job 为 failed
  const result = await p.crawlJob.updateMany({
    where: { status: 'running' },
    data: { status: 'failed', finishedAt: new Date() },
  });
  console.log(`已将 ${result.count} 个卡住的 job 标记为 failed`);
  await p.$disconnect();
}
main().catch(e => { console.error(e); process.exit(1); });
