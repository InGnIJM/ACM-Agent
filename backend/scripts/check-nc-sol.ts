import { PrismaClient } from '@prisma/client';
const p = new PrismaClient();
async function main() {
  const prob = await p.problem.findUnique({
    where: { id: '0a4aa140-a4fa-46e7-b5d3-c11f8d9dfd04' },
    select: {
      sourceId: true, title: true,
      solutions: { select: { id: true } }
    }
  });
  if (prob) {
    console.log(`Problem: ${prob.sourceId} - ${prob.title}`);
    console.log(`Solutions: ${prob.solutions.length}`);
  } else {
    console.log('Problem not found in DB');
  }

  // Check all NC problems without solutions
  const noSols: any[] = await p.$queryRaw`
    SELECT p."source_id", p."title"
    FROM "problems" p
    WHERE p."source_platform" = 'nowcoder'::"Platform"
      AND p."deleted_at" IS NULL
      AND NOT EXISTS (
        SELECT 1 FROM "problem_solutions" ps WHERE ps."problem_id" = p.id
      )
    ORDER BY p."source_id"
  `;
  console.log(`\nNC problems without solutions: ${noSols.length}`);
  for (const r of noSols.slice(0, 20)) {
    console.log(`  ${r.source_id} - ${r.title}`);
  }
  if (noSols.length > 20) console.log(`  ... and ${noSols.length - 20} more`);

  await p.$disconnect();
}
main();
