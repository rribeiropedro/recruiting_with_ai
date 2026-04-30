-- Outreach CRM module — owned by pipeline-outreach-crm.md

-- ─── update_updated_at helper (shared trigger function) ──────────────────────
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$;

-- ─── outreach_campaigns ──────────────────────────────────────────────────────

CREATE TABLE outreach_campaigns (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id                 UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    application_id          UUID NOT NULL REFERENCES generated_applications(id),

    -- Contact info
    contact_name            TEXT,
    contact_title           TEXT,
    contact_email           TEXT,
    contact_linkedin        TEXT,
    email_verified          BOOLEAN DEFAULT FALSE,
    verification_method     TEXT,

    -- Email content
    email_subject           TEXT,
    email_body              TEXT,
    email_html_body         TEXT,
    email_sent_at           TIMESTAMPTZ,
    email_message_id        TEXT,
    email_thread_id         TEXT,

    -- CRM Status
    status                  TEXT NOT NULL DEFAULT 'drafted' CHECK (status IN (
                                'drafted',
                                'queued',
                                'sent',
                                'opened',
                                'responded',
                                'meeting_scheduled',
                                'rejected',
                                'archived'
                            )),

    -- Company research context
    company_context         JSONB,

    -- Error tracking
    send_error              TEXT,

    -- Follow-up tracking
    follow_up_count         INT DEFAULT 0,
    last_follow_up_at       TIMESTAMPTZ,
    next_follow_up_at       TIMESTAMPTZ,

    -- Metadata
    notes                   TEXT,
    created_at              TIMESTAMPTZ DEFAULT NOW(),
    updated_at              TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_campaigns_user_status ON outreach_campaigns(user_id, status);
CREATE INDEX idx_campaigns_application ON outreach_campaigns(application_id);
CREATE INDEX idx_campaigns_email_msg ON outreach_campaigns(email_message_id)
    WHERE email_message_id IS NOT NULL;
CREATE INDEX idx_campaigns_thread ON outreach_campaigns(email_thread_id)
    WHERE email_thread_id IS NOT NULL;

CREATE TRIGGER trg_campaigns_updated_at
    BEFORE UPDATE ON outreach_campaigns
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

ALTER TABLE outreach_campaigns ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can only access their own campaigns"
    ON outreach_campaigns FOR ALL
    USING (auth.uid() = user_id)
    WITH CHECK (auth.uid() = user_id);
