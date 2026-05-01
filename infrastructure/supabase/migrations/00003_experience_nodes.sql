-- Experience Vault module - owned by pipeline-experience-vault.md

CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE EXTENSION IF NOT EXISTS "vector";

CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$;

CREATE TABLE IF NOT EXISTS experience_nodes (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,

    title           TEXT NOT NULL,
    organization    TEXT,
    role            TEXT,
    start_date      DATE,
    end_date        DATE,
    description     TEXT NOT NULL,
    bullet_points   JSONB NOT NULL DEFAULT '[]'::jsonb,
    node_type       TEXT NOT NULL CHECK (node_type IN (
                        'work', 'research', 'project', 'hackathon',
                        'certification', 'education', 'leadership', 'volunteer'
                    )),

    tags            TEXT[] DEFAULT '{}',
    embedding       vector(1536),

    source          TEXT DEFAULT 'manual' CHECK (source IN ('manual', 'bulk_import')),
    metadata        JSONB NOT NULL DEFAULT '{}'::jsonb,
    is_archived     BOOLEAN DEFAULT FALSE,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_nodes_embedding ON experience_nodes
    USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

CREATE INDEX IF NOT EXISTS idx_nodes_user ON experience_nodes(user_id);
CREATE INDEX IF NOT EXISTS idx_nodes_type ON experience_nodes(user_id, node_type);
CREATE INDEX IF NOT EXISTS idx_nodes_tags ON experience_nodes USING gin(tags);
CREATE INDEX IF NOT EXISTS idx_nodes_archived ON experience_nodes(user_id, is_archived);
CREATE INDEX IF NOT EXISTS idx_nodes_matcher_eligible ON experience_nodes(user_id)
    WHERE is_archived = FALSE AND embedding IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_nodes_bulk_import_storage_path
    ON experience_nodes (user_id, (metadata->>'storage_path'))
    WHERE source = 'bulk_import';

-- Dedupe per proposed node, not per resume file; one resume should create many nodes.
CREATE UNIQUE INDEX IF NOT EXISTS idx_nodes_bulk_import_dedup
    ON experience_nodes (user_id, (metadata->>'dedupe_key'))
    WHERE source = 'bulk_import' AND metadata ? 'dedupe_key';

DROP TRIGGER IF EXISTS trg_nodes_updated_at ON experience_nodes;
CREATE TRIGGER trg_nodes_updated_at
    BEFORE UPDATE ON experience_nodes
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

ALTER TABLE experience_nodes ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Users can only access their own nodes" ON experience_nodes;
CREATE POLICY "Users can only access their own nodes"
    ON experience_nodes FOR ALL
    USING (auth.uid() = user_id)
    WITH CHECK (auth.uid() = user_id);

DO $$
BEGIN
    ALTER PUBLICATION supabase_realtime ADD TABLE experience_nodes;
EXCEPTION
    WHEN duplicate_object OR undefined_object THEN NULL;
END;
$$;
