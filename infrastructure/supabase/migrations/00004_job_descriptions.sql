-- Semantic Matcher module - owned by pipeline-semantic-matcher.md

CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE EXTENSION IF NOT EXISTS "vector";

CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$;

CREATE TABLE IF NOT EXISTS job_descriptions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,

    -- Source
    url             TEXT,
    raw_html        TEXT,
    raw_text        TEXT NOT NULL,

    -- Parsed requirements
    company_name    TEXT,
    role_title      TEXT,
    requirements    JSONB NOT NULL DEFAULT '{}'::jsonb,

    -- Matching
    embedding       vector(1536),

    -- Processing status
    status          TEXT NOT NULL DEFAULT 'pending' CHECK (status IN (
                        'pending',
                        'scraping',
                        'extracting',
                        'embedded',
                        'failed'
                    )),
    error_message   TEXT,
    celery_task_id  TEXT,

    -- Housekeeping
    scraped_at      TIMESTAMPTZ,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_jobs_user ON job_descriptions(user_id);
CREATE INDEX IF NOT EXISTS idx_jobs_user_status ON job_descriptions(user_id, status);
CREATE INDEX IF NOT EXISTS idx_jobs_embedding ON job_descriptions
    USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);
CREATE INDEX IF NOT EXISTS idx_jobs_url ON job_descriptions(user_id, url)
    WHERE url IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_jobs_recent_url ON job_descriptions(user_id, url, created_at DESC)
    WHERE url IS NOT NULL;

DROP TRIGGER IF EXISTS trg_jobs_updated_at ON job_descriptions;
CREATE TRIGGER trg_jobs_updated_at
    BEFORE UPDATE ON job_descriptions
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

ALTER TABLE job_descriptions ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Users can only access their own jobs" ON job_descriptions;
CREATE POLICY "Users can only access their own jobs"
    ON job_descriptions FOR ALL
    USING (auth.uid() = user_id)
    WITH CHECK (auth.uid() = user_id);

DO $$
BEGIN
    ALTER PUBLICATION supabase_realtime ADD TABLE job_descriptions;
EXCEPTION
    WHEN duplicate_object OR undefined_object THEN NULL;
END;
$$;
