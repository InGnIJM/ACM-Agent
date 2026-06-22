-- PGVector HNSW indexes + GIN index for RAG hybrid search
-- pgvector 0.8.2, PostgreSQL 18
-- Run AFTER data migration (vectors must exist before building HNSW)

DROP INDEX IF EXISTS idx_problems_vector_embedding_ivfflat;

-- Solution vector HNSW (retrieval_summary embedding)
CREATE INDEX IF NOT EXISTS idx_problems_solution_vector_hnsw
ON public.problems USING hnsw (vector_embedding vector_cosine_ops)
WITH (m = 16, ef_construction = 64)
WHERE deleted_at IS NULL AND vector_embedding IS NOT NULL;

-- Content vector HNSW (full_content embedding)
CREATE INDEX IF NOT EXISTS idx_problems_content_vector_hnsw
ON public.problems USING hnsw (content_vector vector_cosine_ops)
WITH (m = 16, ef_construction = 64)
WHERE deleted_at IS NULL AND content_vector IS NOT NULL;

-- Solution summary vector HNSW (problem_solutions)
CREATE INDEX IF NOT EXISTS idx_problem_solutions_summary_vector_hnsw
ON public.problem_solutions USING hnsw (summary_vector vector_cosine_ops)
WITH (m = 16, ef_construction = 64)
WHERE deleted_at IS NULL AND summary_vector IS NOT NULL;

-- Sparse text GIN for keyword search
CREATE INDEX IF NOT EXISTS idx_problems_sparse_text_gin
ON public.problems USING gin (to_tsvector('simple', coalesce(sparse_text, '')))
WHERE deleted_at IS NULL;
