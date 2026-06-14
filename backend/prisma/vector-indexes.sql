-- PGVector IVFFlat indexes for semantic search
-- Run after: CREATE EXTENSION IF NOT EXISTS vector;
-- Prerequisites: tables must have data before creating IVFFlat indexes (lists parameter depends on row count)

CREATE INDEX IF NOT EXISTS idx_problems_vector_embedding ON problems USING ivfflat (vector_embedding vector_cosine_ops) WITH (lists = 100);
CREATE INDEX IF NOT EXISTS idx_problems_content_vector ON problems USING ivfflat (content_vector vector_cosine_ops) WITH (lists = 100);
CREATE INDEX IF NOT EXISTS idx_problem_solutions_vector ON problem_solutions USING ivfflat (vector_embedding vector_cosine_ops) WITH (lists = 50);
