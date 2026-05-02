-- Document Assembly module - owned by pipeline-document-assembly.md

CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE EXTENSION IF NOT EXISTS "vector";

CREATE TABLE IF NOT EXISTS generated_applications (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id                 UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    job_description_id      UUID NOT NULL REFERENCES job_descriptions(id),

    -- Generation details
    matched_node_ids        UUID[] NOT NULL DEFAULT '{}',
    similarity_scores       FLOAT[] NOT NULL DEFAULT '{}',
    tailored_content        JSONB NOT NULL DEFAULT '{}'::jsonb,

    -- Output
    pdf_storage_path        TEXT,
    pdf_url                 TEXT,
    resume_text             TEXT,
    resume_embedding        vector(1536),
    job_embedding_snapshot  vector(1536),
    resume_summary          TEXT,

    -- Caching
    cache_hit               BOOLEAN DEFAULT FALSE,
    cache_source_id         UUID REFERENCES generated_applications(id),

    -- Status tracking
    status                  TEXT NOT NULL DEFAULT 'pending' CHECK (status IN (
                                'pending',
                                'scraping',
                                'extracting',
                                'matching',
                                'rewriting',
                                'rendering',
                                'completed',
                                'failed'
                            )),
    error_message           TEXT,
    celery_task_id          TEXT,

    created_at              TIMESTAMPTZ DEFAULT NOW(),
    completed_at            TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_apps_user ON generated_applications(user_id);
CREATE INDEX IF NOT EXISTS idx_apps_status ON generated_applications(user_id, status);
CREATE INDEX IF NOT EXISTS idx_apps_job ON generated_applications(job_description_id);
CREATE INDEX IF NOT EXISTS idx_apps_resume_emb ON generated_applications
    USING hnsw (resume_embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);
CREATE INDEX IF NOT EXISTS idx_apps_job_emb ON generated_applications
    USING hnsw (job_embedding_snapshot vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

ALTER TABLE generated_applications ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Users can only access their own applications" ON generated_applications;
CREATE POLICY "Users can only access their own applications"
    ON generated_applications FOR ALL
    USING (auth.uid() = user_id)
    WITH CHECK (auth.uid() = user_id);

DO $$
BEGIN
    ALTER PUBLICATION supabase_realtime ADD TABLE generated_applications;
EXCEPTION
    WHEN duplicate_object OR undefined_object THEN NULL;
END;
$$;
