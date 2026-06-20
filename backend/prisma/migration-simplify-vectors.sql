-- Migration: simplify RAG vectors — keep only problem solution_summary vector
-- Drops: problems.content_vector, problem_solutions.vector_embedding
-- Run after updating schema.prisma and before npx prisma db push

-- Drop old indexes first
DROP INDEX IF EXISTS idx_problems_content_vector;
DROP INDEX IF EXISTS idx_problem_solutions_vector;

-- Drop old columns
ALTER TABLE problems DROP COLUMN IF EXISTS content_vector;
ALTER TABLE problem_solutions DROP COLUMN IF EXISTS vector_embedding;
