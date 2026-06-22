-- ============================================================
-- RAG Upgrade: 新增字段 + 迁移日志表
-- 幂等（全部 ADD COLUMN IF NOT EXISTS / CREATE TABLE IF NOT EXISTS）
-- pgvector 0.8.2 + PostgreSQL 18
-- ============================================================

-- problems 新增字段
ALTER TABLE public.problems ADD COLUMN IF NOT EXISTS retrieval_summary text;
ALTER TABLE public.problems ADD COLUMN IF NOT EXISTS sparse_text text;
ALTER TABLE public.problems ADD COLUMN IF NOT EXISTS summary_struct jsonb;
ALTER TABLE public.problems ADD COLUMN IF NOT EXISTS primary_algo varchar(50);
ALTER TABLE public.problems ADD COLUMN IF NOT EXISTS sub_algos text[];
ALTER TABLE public.problems ADD COLUMN IF NOT EXISTS problem_patterns text[];
ALTER TABLE public.problems ADD COLUMN IF NOT EXISTS retrieval_summary_generated_at timestamptz;
ALTER TABLE public.problems ADD COLUMN IF NOT EXISTS embedding_generated_at timestamptz;
ALTER TABLE public.problems ADD COLUMN IF NOT EXISTS embedding_version varchar(100);
ALTER TABLE public.problems ADD COLUMN IF NOT EXISTS retrieval_version varchar(100);
ALTER TABLE public.problems ADD COLUMN IF NOT EXISTS content_vector vector(1024);

-- problem_solutions 新增字段
ALTER TABLE public.problem_solutions ADD COLUMN IF NOT EXISTS summary text;
ALTER TABLE public.problem_solutions ADD COLUMN IF NOT EXISTS summary_vector vector(1024);
ALTER TABLE public.problem_solutions ADD COLUMN IF NOT EXISTS quality_score double precision;
ALTER TABLE public.problem_solutions ADD COLUMN IF NOT EXISTS solution_type varchar(50);
ALTER TABLE public.problem_solutions ADD COLUMN IF NOT EXISTS extracted_algos text[];
ALTER TABLE public.problem_solutions ADD COLUMN IF NOT EXISTS summary_generated_at timestamptz;
ALTER TABLE public.problem_solutions ADD COLUMN IF NOT EXISTS embedding_generated_at timestamptz;
ALTER TABLE public.problem_solutions ADD COLUMN IF NOT EXISTS embedding_version varchar(100);

-- 迁移日志表
CREATE TABLE IF NOT EXISTS public.rag_migration_logs (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    problem_id uuid REFERENCES public.problems(id),
    solution_id uuid REFERENCES public.problem_solutions(id),
    stage varchar(100) NOT NULL,
    status varchar(50) NOT NULL,
    message text,
    old_version varchar(100),
    new_version varchar(100),
    duration_ms integer,
    started_at timestamptz NOT NULL DEFAULT now(),
    finished_at timestamptz,
    UNIQUE (problem_id, stage)
);

CREATE INDEX IF NOT EXISTS idx_rag_migration_logs_stage_status
ON public.rag_migration_logs (stage, status);

CREATE INDEX IF NOT EXISTS idx_rag_migration_logs_problem_id
ON public.rag_migration_logs (problem_id);
