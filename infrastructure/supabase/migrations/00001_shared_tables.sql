-- Shared tables owned by architecture.md (not any single pipeline)

CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE EXTENSION IF NOT EXISTS "vector";

-- ─── user_profiles ───────────────────────────────────────────────────────────

CREATE TABLE user_profiles (
    user_id             UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    full_name           TEXT NOT NULL,
    email               TEXT NOT NULL,
    phone               TEXT,
    location            TEXT,
    linkedin_url        TEXT,
    portfolio_url       TEXT,
    github_url          TEXT,
    headline            TEXT,
    gmail_oauth_token   JSONB,
    outlook_oauth_token JSONB,
    preferred_template  TEXT DEFAULT 'modern',
    target_industries   TEXT[] DEFAULT '{}',
    target_roles        TEXT[] DEFAULT '{}',
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    updated_at          TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE user_profiles ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can only access their own rows"
    ON user_profiles FOR ALL
    USING (auth.uid() = user_id)
    WITH CHECK (auth.uid() = user_id);

-- ─── llm_usage ───────────────────────────────────────────────────────────────

CREATE TABLE llm_usage (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES auth.users(id),
    task_type       TEXT NOT NULL,
    model           TEXT NOT NULL,
    input_tokens    INT NOT NULL,
    output_tokens   INT NOT NULL,
    cost_usd        DECIMAL(10, 6),
    prompt_version  TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE llm_usage ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can only access their own rows"
    ON llm_usage FOR ALL
    USING (auth.uid() = user_id)
    WITH CHECK (auth.uid() = user_id);
