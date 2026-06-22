import { PrismaClient } from '@prisma/client';

const prisma = new PrismaClient();

async function main() {
  const p = await prisma.problem.findUnique({
    where: { id: '0023e738-3115-4eae-8ee0-c8cfee422504' },
    include: { solutions: true }
  });
  if (!p) { console.log('NOT FOUND'); await prisma.$disconnect(); return; }

  console.log('=== 基本信息 ===');
  console.log('title:', p.title);
  console.log('platform:', p.sourcePlatform);
  console.log('sourceId:', p.sourceId);
  console.log('difficulty:', p.difficultyNormalized);
  console.log('tags:', p.tagsNormalized);
  console.log('sourceUrl:', p.sourceUrl);
  console.log('');

  console.log('=== solution_summary (父段文本) ===');
  console.log('length:', (p.solutionSummary || '').length);
  console.log(p.solutionSummary);
  console.log('');

  console.log('=== vector_embedding (父向量) ===');
  console.log('has vector:', !!p.vectorEmbedding);
  console.log('');

  console.log('=== full_content (内容段文本) 前800字符 ===');
  console.log('length:', (p.fullContent || '').length);
  console.log((p.fullContent || '').substring(0, 800));
  console.log('');

  console.log('=== content_vector (内容向量) ===');
  console.log('has vector:', !!p.contentVector);
  console.log('');

  console.log('=== solutions (子段) ===');
  console.log('count:', p.solutions.length);
  p.solutions.forEach((s: any, i: number) => {
    console.log(`\n--- solution #${i} ---`);
    console.log('author:', s.author);
    console.log('content length:', (s.content || '').length);
    console.log('has vector:', !!s.vectorEmbedding);
    console.log('content preview (前400字):');
    console.log((s.content || '').substring(0, 400));
  });

  await prisma.$disconnect();
}

main().catch(e => { console.error(e); process.exit(1); });
