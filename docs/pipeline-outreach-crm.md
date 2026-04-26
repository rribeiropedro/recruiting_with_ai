# Pipeline: Outreach AI & Execution CRM

> **Prerequisite:** Read `architecture.md` sections 1-3 for platform context, tech stack, and shared conventions.
>
> **Scope:** This document fully specifies the Outreach CRM module — the pipeline that discovers hiring managers, drafts cold emails, sends from the user's inbox, and tracks responses in a Kanban dashboard. An agent with this doc and the architecture doc can build the entire module without consulting any other pipeline doc.
>
> **Owns:** Route groups `/outreach/*`, `/user/oauth/*` · Table `outreach_campaigns` · Services `contact_finder.py`, `email_drafter.py`, `email_sender.py` · Tasks `outreach_tasks.py` · Prompts `draft_email.py` · Frontend pages `app/(auth)/outreach/*` · Components `components/crm/*`
>
> **Depends on:** Document Assembly pipeline (provides `GeneratedApplicationSummary`). This module consumes the generated PDF and tailored resume text to draft emails. It reads `generated_applications` and `job_descriptions` but never writes to them.

---

## 1. Purpose

Close the loop from resume generation to actual outreach. This module handles four concerns:

1. **Contact Discovery** — Find and verify the hiring manager's email address.
2. **Email Drafting** — Use RAG to draft a personalized, non-generic cold email.
3. **Email Sending** — Send from the user's own Gmail/Outlook inbox via OAuth.
4. **Campaign Tracking** — Real-time Kanban CRM dashboard with reply detection.

---

## 2. Database Schema

### 2.1 `outreach_campaigns` Table

```sql
CREATE TABLE outreach_campaigns (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id                 UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    application_id          UUID NOT NULL REFERENCES generated_applications(id),

    -- Contact info
    contact_name            TEXT,
    contact_title           TEXT,                           -- "Engineering Manager"
    contact_email           TEXT,
    contact_linkedin        TEXT,
    email_verified          BOOLEAN DEFAULT FALSE,
    verification_method     TEXT,                           -- "hunter", "apollo", "manual", null

    -- Email content
    email_subject           TEXT,
    email_body              TEXT,
    email_html_body         TEXT,                           -- Optional HTML version for rich email
    email_sent_at           TIMESTAMPTZ,
    email_message_id        TEXT,                           -- Gmail/Outlook msg ID for reply tracking
    email_thread_id         TEXT,                           -- Gmail thread ID

    -- CRM Status
    status                  TEXT NOT NULL DEFAULT 'drafted' CHECK (status IN (
                                'drafted',              -- Email drafted, not yet sent
                                'queued',               -- User approved, queued for sending
                                'sent',                 -- Email sent successfully
                                'opened',               -- Open tracked (stretch goal)
                                'responded',            -- Reply detected
                                'meeting_scheduled',    -- User manually marked
                                'rejected',             -- User manually marked
                                'archived'              -- User manually archived
                            )),

    -- Company research context (used for drafting)
    company_context         JSONB,
    -- Schema:
    -- {
    --   "recent_news": ["Article title 1", "Article title 2"],
    --   "company_description": "...",
    --   "funding_stage": "Series B",
    --   "employee_count": "50-200",
    --   "industry": "fintech"
    -- }

    -- Follow-up tracking
    follow_up_count         INT DEFAULT 0,
    last_follow_up_at       TIMESTAMPTZ,
    next_follow_up_at       TIMESTAMPTZ,                   -- Scheduled follow-up (stretch goal)

    -- Metadata
    notes                   TEXT,                           -- User's private notes
    created_at              TIMESTAMPTZ DEFAULT NOW(),
    updated_at              TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes
CREATE INDEX idx_campaigns_user_status ON outreach_campaigns(user_id, status);
CREATE INDEX idx_campaigns_application ON outreach_campaigns(application_id);
CREATE INDEX idx_campaigns_email_msg ON outreach_campaigns(email_message_id)
    WHERE email_message_id IS NOT NULL;
CREATE INDEX idx_campaigns_thread ON outreach_campaigns(email_thread_id)
    WHERE email_thread_id IS NOT NULL;

-- Updated-at trigger (reuse from architecture.md)
CREATE TRIGGER trg_campaigns_updated_at
    BEFORE UPDATE ON outreach_campaigns
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();
```

### 2.2 RLS Policy

```sql
ALTER TABLE outreach_campaigns ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can only access their own campaigns"
    ON outreach_campaigns FOR ALL
    USING (auth.uid() = user_id)
    WITH CHECK (auth.uid() = user_id);
```

---

## 3. Pydantic Schemas

### 3.1 Request Schemas

```python
# schemas/outreach.py
class CampaignCreateRequest(BaseModel):
    application_id: UUID
    contact_name: str | None = None
    contact_email: str | None = Field(None, pattern=r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$")
    contact_title: str | None = None
    contact_linkedin: str | None = None
    auto_discover_contact: bool = True  # If true, attempt to find contact automatically

class CampaignUpdateRequest(BaseModel):
    status: str | None = Field(None, pattern="^(drafted|queued|meeting_scheduled|rejected|archived)$")
    contact_name: str | None = None
    contact_email: str | None = None
    contact_title: str | None = None
    notes: str | None = None

class DraftEmailRequest(BaseModel):
    """Trigger email draft generation (or regeneration)."""
    tone: str = "conversational"  # "conversational" | "professional" | "bold"

class SendEmailRequest(BaseModel):
    provider: str = "gmail"  # "gmail" | "outlook"
    attach_resume: bool = True
```

### 3.2 Response Schemas

```python
class CampaignResponse(BaseModel):
    id: UUID
    application_id: UUID
    company_name: str | None        # Denormalized from job_descriptions
    role_title: str | None
    contact_name: str | None
    contact_title: str | None
    contact_email: str | None
    email_verified: bool
    email_subject: str | None
    email_body: str | None
    status: str
    follow_up_count: int
    notes: str | None
    created_at: datetime
    updated_at: datetime

class CampaignListResponse(BaseModel):
    campaigns: list[CampaignResponse]
    counts: dict[str, int]          # {"drafted": 5, "sent": 12, "responded": 3, ...}

class EmailDraftResponse(BaseModel):
    campaign_id: UUID
    email_subject: str
    email_body: str
    company_context_used: dict     # What context was injected
    tone: str

class SendResultResponse(BaseModel):
    success: bool
    email_message_id: str | None
    error: str | None              # "token_expired", "rate_limited", "send_failed"
```

---

## 4. API Endpoints

Base path: `/outreach`

### 4.1 Create Campaign

```
POST /outreach/campaigns
Auth: Required
Body: CampaignCreateRequest
Returns: 201 + CampaignResponse
Side effects: If auto_discover_contact=true, dispatches discover_contact_task
```

### 4.2 List Campaigns

```
GET /outreach/campaigns?status={status}&cursor={uuid}&limit={int}
Auth: Required
Returns: 200 + CampaignListResponse
```

**The `counts` field** provides a count per status for the Kanban column headers. Computed via:

```sql
SELECT status, COUNT(*) FROM outreach_campaigns
WHERE user_id = $1
GROUP BY status;
```

### 4.3 Get Campaign

```
GET /outreach/campaigns/{id}
Auth: Required
Returns: 200 + CampaignResponse (with full email body)
```

### 4.4 Update Campaign

```
PATCH /outreach/campaigns/{id}
Auth: Required
Body: CampaignUpdateRequest
Returns: 200 + CampaignResponse
```

Used for: manual status changes (drag-and-drop in Kanban), editing contact info, adding notes.

### 4.5 Draft Email

```
POST /outreach/campaigns/{id}/draft
Auth: Required
Body: DraftEmailRequest
Returns: 200 + EmailDraftResponse
Side effects: Dispatches draft_email_task, waits synchronously (sub-15s)
              OR dispatches async and returns 202 with task_id
```

**Design decision:** Email drafting is fast enough (5-10s) to run synchronously with a loading spinner. If latency is unacceptable, switch to async + polling.

### 4.6 Send Email

```
POST /outreach/campaigns/{id}/send
Auth: Required
Body: SendEmailRequest
Returns: 200 + SendResultResponse
Errors: 401 if OAuth token expired (client should trigger re-auth)
        409 if campaign already sent
        422 if no contact_email or no email_body
```

### 4.7 Gmail OAuth Flow

```
POST /user/oauth/gmail/initiate
Auth: Required
Returns: 200 + { auth_url: str }
Action: Generate Google OAuth URL with state=user_id, redirect to it

GET /user/oauth/gmail/callback?code={code}&state={state}
Returns: 302 redirect to frontend with success/error query param
Action: Exchange code for tokens, encrypt and store in user_profiles.gmail_oauth_token
```

### 4.8 Outlook OAuth Flow (Same pattern)

```
POST /user/oauth/outlook/initiate → { auth_url }
GET /user/oauth/outlook/callback → 302 redirect
```

### 4.9 Check OAuth Status

```
GET /user/oauth/status
Auth: Required
Returns: 200 + { gmail_connected: bool, outlook_connected: bool }
```

---

## 5. Services

### 5.1 Contact Finder (`services/contact_finder.py`)

```python
class ContactFinder:
    async def discover(self, company_name: str, role_title: str) -> ContactResult | None:
        """Find the hiring manager's email for a given company and role."""

        # Step 1: Infer company domain
        domain = await self._find_domain(company_name)
        if not domain:
            return None

        # Step 2: Search Hunter.io
        contact = await self._hunter_search(domain, role_title)
        if contact:
            return contact

        # Step 3: Fallback to Apollo.io
        contact = await self._apollo_search(company_name, role_title)
        if contact:
            return contact

        return None

    async def _find_domain(self, company_name: str) -> str | None:
        """Use Hunter's company search to find the domain."""
        response = await httpx_client.get(
            "https://api.hunter.io/v2/domain-search",
            params={"company": company_name, "api_key": settings.HUNTER_API_KEY},
        )
        data = response.json()
        return data.get("data", {}).get("domain")

    async def _hunter_search(self, domain: str, role_title: str) -> ContactResult | None:
        """Search Hunter.io for contacts at the domain, filter by title."""
        response = await httpx_client.get(
            "https://api.hunter.io/v2/domain-search",
            params={
                "domain": domain,
                "api_key": settings.HUNTER_API_KEY,
                "limit": 10,
            },
        )
        contacts = response.json().get("data", {}).get("emails", [])

        # Priority title keywords (ordered by preference)
        title_keywords = [
            "hiring manager", "recruiter", "talent acquisition",
            "engineering manager", "head of engineering",
            "vp engineering", "director of engineering",
            "cto", "head of talent",
        ]

        # Score contacts by title relevance
        best = None
        best_score = -1
        for c in contacts:
            title = (c.get("position") or "").lower()
            for i, kw in enumerate(title_keywords):
                if kw in title:
                    score = len(title_keywords) - i  # Higher = better
                    if score > best_score:
                        best = c
                        best_score = score
                    break

        if not best:
            return None

        # Verify email
        verified = await self._verify_email(best["value"])

        return ContactResult(
            name=f"{best.get('first_name', '')} {best.get('last_name', '')}".strip(),
            title=best.get("position"),
            email=best["value"],
            verified=verified,
            method="hunter",
            linkedin=best.get("linkedin"),
        )

    async def _verify_email(self, email: str) -> bool:
        """Verify email deliverability via Hunter."""
        response = await httpx_client.get(
            "https://api.hunter.io/v2/email-verifier",
            params={"email": email, "api_key": settings.HUNTER_API_KEY},
        )
        result = response.json().get("data", {}).get("result")
        return result in ("deliverable", "risky")  # Accept "risky" — better than nothing

    async def _apollo_search(self, company_name: str, role_title: str) -> ContactResult | None:
        """Fallback: search Apollo.io for contacts."""
        response = await httpx_client.post(
            "https://api.apollo.io/v1/mixed_people/search",
            headers={"Content-Type": "application/json", "Cache-Control": "no-cache"},
            json={
                "api_key": settings.APOLLO_API_KEY,
                "q_organization_name": company_name,
                "person_titles": ["Engineering Manager", "Hiring Manager", "Recruiter",
                                  "Head of Engineering", "VP Engineering"],
                "page": 1,
                "per_page": 5,
            },
        )
        people = response.json().get("people", [])
        if not people:
            return None

        person = people[0]
        return ContactResult(
            name=person.get("name"),
            title=person.get("title"),
            email=person.get("email"),
            verified=person.get("email") is not None,
            method="apollo",
            linkedin=person.get("linkedin_url"),
        )
```

### 5.2 Email Drafter (`services/email_drafter.py`)

```python
class EmailDrafter:
    async def draft(
        self,
        campaign: OutreachCampaign,
        application_summary: GeneratedApplicationSummary,
        job_requirements: JobRequirements,
        user_profile: UserProfile,
        tone: str = "conversational",
    ) -> EmailDraft:
        """Draft a cold email using RAG."""

        # Step 1: Gather company context
        company_context = await self._research_company(
            job_requirements.company_name,
            job_requirements.industry,
        )

        # Step 2: Build the prompt
        user_prompt = self._build_prompt(
            company_name=job_requirements.company_name,
            company_context=company_context,
            contact_name=campaign.contact_name,
            contact_title=campaign.contact_title,
            role_title=job_requirements.role_title,
            resume_summary=application_summary.resume_text_summary,
            user_name=user_profile.full_name,
            tone=tone,
        )

        # Step 3: Call LLM
        response = llm_client.complete(
            system_prompt=DRAFT_EMAIL_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            model="claude-sonnet-4-20250514",
            user_id=campaign.user_id,
            task_type="draft_email",
            prompt_version=DRAFT_EMAIL_VERSION,
        )

        # Step 4: Parse subject + body
        subject, body = self._parse_email(response, job_requirements.role_title, user_profile.full_name)

        return EmailDraft(
            subject=subject,
            body=body,
            company_context=company_context,
        )

    async def _research_company(self, company_name: str | None, industry: str | None) -> dict:
        """Gather recent company context for the email hook."""
        if not company_name:
            return {}

        # Check cache first
        cache_key = f"company_ctx:{company_name.lower().replace(' ', '_')}"
        cached = await redis.get(cache_key)
        if cached:
            return json.loads(cached)

        # Web search for recent news (use a lightweight search API or scraper)
        # This is a simplified version — in production, use Serper API or similar
        context = {
            "company_name": company_name,
            "industry": industry,
            "recent_news": [],
            "company_description": "",
        }

        try:
            # Search for recent news
            news_results = await web_search(f"{company_name} recent news 2026")
            context["recent_news"] = [r["title"] for r in news_results[:3]]

            # Search for company info
            info_results = await web_search(f"{company_name} company about")
            if info_results:
                context["company_description"] = info_results[0].get("snippet", "")
        except Exception:
            pass  # Company context is nice-to-have, not critical

        # Cache for 24 hours
        await redis.setex(cache_key, 86400, json.dumps(context))
        return context

    def _build_prompt(self, **kwargs) -> str:
        parts = [
            f"COMPANY: {kwargs['company_name'] or 'Unknown'}",
            f"COMPANY CONTEXT: {json.dumps(kwargs['company_context'])}",
            f"HIRING MANAGER: {kwargs['contact_name'] or 'Hiring Manager'}, {kwargs['contact_title'] or 'unknown title'}",
            f"ROLE: {kwargs['role_title'] or 'the open position'}",
            f"CANDIDATE NAME: {kwargs['user_name']}",
            f"CANDIDATE RESUME SUMMARY:\n{kwargs['resume_summary']}",
            f"TONE: {kwargs['tone']}",
        ]
        return "\n\n".join(parts)

    def _parse_email(self, raw_response: str, role_title: str | None, user_name: str) -> tuple[str, str]:
        """Parse the LLM response into subject and body."""
        lines = raw_response.strip().split("\n")

        # Try to find a "Subject:" line
        subject = None
        body_start = 0
        for i, line in enumerate(lines):
            if line.lower().startswith("subject:"):
                subject = line.split(":", 1)[1].strip()
                body_start = i + 1
                break

        if not subject:
            subject = f"Re: {role_title or 'Open Position'} — {user_name}"

        body = "\n".join(lines[body_start:]).strip()
        return subject, body
```

### 5.3 Email Sender (`services/email_sender.py`)

```python
class EmailSender:
    async def send_gmail(
        self,
        user_profile: UserProfile,
        to_email: str,
        subject: str,
        body: str,
        attachment: tuple[str, bytes] | None = None,  # (filename, pdf_bytes)
    ) -> SendResult:
        """Send email via Gmail API using user's OAuth token."""

        # Decrypt OAuth token
        token_data = decrypt_oauth_token(user_profile.gmail_oauth_token)
        if not token_data:
            return SendResult(success=False, error="token_expired")

        # Refresh token if needed
        creds = Credentials(
            token=token_data["access_token"],
            refresh_token=token_data["refresh_token"],
            token_uri="https://oauth2.googleapis.com/token",
            client_id=settings.GOOGLE_OAUTH_CLIENT_ID,
            client_secret=settings.GOOGLE_OAUTH_CLIENT_SECRET,
        )
        if creds.expired:
            try:
                creds.refresh(Request())
                # Update stored token
                new_token_data = {
                    "access_token": creds.token,
                    "refresh_token": creds.refresh_token,
                }
                await db.update_user_profile(user_profile.user_id,
                    gmail_oauth_token=encrypt_oauth_token(new_token_data))
            except RefreshError:
                return SendResult(success=False, error="token_expired")

        # Build MIME message
        message = MIMEMultipart()
        message["to"] = to_email
        message["from"] = user_profile.email
        message["subject"] = subject
        message.attach(MIMEText(body, "plain"))

        if attachment:
            filename, pdf_bytes = attachment
            att = MIMEBase("application", "pdf")
            att.set_payload(pdf_bytes)
            encoders.encode_base64(att)
            att.add_header("Content-Disposition", f"attachment; filename={filename}")
            message.attach(att)

        # Send via Gmail API
        service = build("gmail", "v1", credentials=creds)
        raw = base64.urlsafe_b64encode(message.as_bytes()).decode()

        try:
            sent = service.users().messages().send(
                userId="me",
                body={"raw": raw},
            ).execute()
            return SendResult(
                success=True,
                message_id=sent["id"],
                thread_id=sent.get("threadId"),
            )
        except HttpError as e:
            if e.resp.status == 429:
                return SendResult(success=False, error="rate_limited")
            return SendResult(success=False, error=f"send_failed: {str(e)}")

    async def send_outlook(self, user_profile, to_email, subject, body, attachment=None):
        """Send via Microsoft Graph API. Same pattern as Gmail."""
        # Implementation follows same structure using Microsoft Graph SDK
        # POST https://graph.microsoft.com/v1.0/me/sendMail
        ...
```

---

## 6. Background Tasks

### 6.1 `discover_contact_task`

| Property | Value |
|---|---|
| Queue | `default` |
| Typical duration | 3-10s |
| Retry policy | 1 retry, delay 10s |
| Idempotent | Yes — overwrites contact fields |

```python
@celery_app.task(bind=True, max_retries=1)
def discover_contact_task(self, campaign_id: str):
    campaign = db.get_campaign(campaign_id)
    app = db.get_application(campaign.application_id)
    job = db.get_job(app.job_description_id)

    contact = contact_finder.discover(
        company_name=job.company_name,
        role_title=job.role_title,
    )

    if contact:
        db.update_campaign(campaign_id,
            contact_name=contact.name,
            contact_title=contact.title,
            contact_email=contact.email,
            contact_linkedin=contact.linkedin,
            email_verified=contact.verified,
            verification_method=contact.method,
        )
    # If no contact found, campaign keeps contact_email = NULL
    # User can fill it in manually via the UI
```

### 6.2 `draft_email_task`

| Property | Value |
|---|---|
| Queue | `default` |
| Typical duration | 5-10s |
| Retry policy | 2 retries, delays: 5s, 15s |
| Idempotent | Yes — overwrites email_subject, email_body |

### 6.3 `send_email_task`

| Property | Value |
|---|---|
| Queue | `email` |
| Typical duration | 2-5s |
| Retry policy | **0 retries** — emails must never be sent twice |
| Idempotent | **No** — check status before sending |

```python
@celery_app.task(bind=True, max_retries=0)
def send_email_task(self, campaign_id: str, provider: str = "gmail", attach_resume: bool = True):
    campaign = db.get_campaign(campaign_id)

    # Guard: don't double-send
    if campaign.status in ("sent", "responded", "meeting_scheduled"):
        return

    if not campaign.contact_email or not campaign.email_body:
        db.update_campaign(campaign_id, status="drafted")  # Reset
        return

    # Get resume PDF if attaching
    attachment = None
    if attach_resume:
        app = db.get_application(campaign.application_id)
        if app.pdf_storage_path:
            pdf_bytes = storage.download(app.pdf_storage_path)
            filename = f"{user_profile.full_name.replace(' ', '_')}_Resume.pdf"
            attachment = (filename, pdf_bytes)

    user_profile = db.get_user_profile(campaign.user_id)

    if provider == "gmail":
        result = email_sender.send_gmail(
            user_profile, campaign.contact_email,
            campaign.email_subject, campaign.email_body,
            attachment,
        )
    else:
        result = email_sender.send_outlook(...)

    if result.success:
        db.update_campaign(campaign_id,
            status="sent",
            email_sent_at=datetime.utcnow(),
            email_message_id=result.message_id,
            email_thread_id=result.thread_id,
        )
    else:
        # Don't retry — surface error to user
        db.update_campaign(campaign_id, status="drafted")
        # The API endpoint returns the error to the frontend
```

---

## 7. LLM Prompts

### 7.1 `draft_email.py`

```python
VERSION = "draft_email_v1"

SYSTEM_PROMPT = """You are a professional cold email writer. Draft a concise cold email
(under 150 words) from a job candidate to a hiring manager.

Format your response as:
Subject: [subject line]

[email body]

The email must:
1. Open with a specific, genuine hook about the company — reference a real detail from the
   COMPANY CONTEXT provided (a product, a blog post, a funding round, a recent achievement).
   If no context is available, reference something specific about the role instead.
   NEVER use generic openers.
2. Bridge to the candidate's most relevant 1-2 achievements from the RESUME SUMMARY (1-2 sentences).
   Use specific numbers or outcomes if available.
3. Include a clear, low-friction call to action: "Would you be open to a 15-minute chat
   this week?" or similar. ONE question only.
4. Close with the candidate's name. No "Best regards" or "Sincerely" — just the name.

TONE RULES:
- Match the TONE parameter: "conversational" = casual but professional, "professional" =
  polished but not stiff, "bold" = confident and direct.
- Write like a real human, not a template or an AI.
- No buzzwords: NEVER use "synergy", "leverage", "passionate about", "excited to",
  "thrilled", "delighted".
- No "I hope this email finds you well" or ANY variant of it.
- No "I came across your posting" — too generic.
- First person, active voice throughout.
- Short paragraphs: 2-3 sentences max per paragraph. Total email: 3-4 paragraphs.
- If the hiring manager's name is unknown, address as "Hi there" — never "Dear Hiring Manager".

CRITICAL: The email must feel like it was written by the candidate, not by an AI.
A human reading this should not suspect it was generated."""
```

---

## 8. OAuth Implementation

### 8.1 Gmail OAuth Flow

**Scopes required:**

```python
GMAIL_SCOPES = [
    "https://www.googleapis.com/auth/gmail.send",      # Send emails
    "https://www.googleapis.com/auth/gmail.readonly",   # Reply detection (stretch)
]
```

**Token encryption:** All OAuth tokens are encrypted with `cryptography.fernet` before storage. The Fernet key is derived from `ENCRYPTION_KEY` env var.

```python
from cryptography.fernet import Fernet

def encrypt_oauth_token(token_data: dict) -> str:
    f = Fernet(settings.ENCRYPTION_KEY.encode())
    return f.encrypt(json.dumps(token_data).encode()).decode()

def decrypt_oauth_token(encrypted: str) -> dict | None:
    try:
        f = Fernet(settings.ENCRYPTION_KEY.encode())
        return json.loads(f.decrypt(encrypted.encode()))
    except Exception:
        return None
```

### 8.2 Outlook OAuth Flow

**Scopes:** `Mail.Send`, `Mail.Read` (for reply detection).

**Implementation:** Same pattern as Gmail but using Microsoft Identity Platform endpoints and Microsoft Graph API.

### 8.3 Token Refresh Strategy

- Before every send, check if the access token is expired.
- If expired, use the refresh token to get a new access token.
- If refresh fails (user revoked access), return `error: "token_expired"` and prompt re-auth in the UI.

---

## 9. Reply Detection (Stretch Goal)

### 9.1 Gmail Push Notifications

Set up Gmail push notifications via Google Pub/Sub to detect replies:

1. Create a Pub/Sub topic and subscription in Google Cloud.
2. When user connects Gmail, call `users.watch()` to subscribe to inbox changes.
3. When a notification arrives, check if the thread ID matches any `outreach_campaigns.email_thread_id`.
4. If match found, update `status = 'responded'` and increment `follow_up_count`.

### 9.2 Outlook Subscriptions

Use Microsoft Graph subscriptions (`/subscriptions`) to watch for new messages in the inbox. Same matching logic as Gmail.

### 9.3 Polling Fallback

If push notifications are too complex for MVP, poll every 15 minutes:

```python
@celery_app.task
def check_replies_task():
    """Periodic task — runs every 15 minutes."""
    sent_campaigns = db.get_campaigns_by_status("sent")
    for campaign in sent_campaigns:
        if not campaign.email_thread_id:
            continue
        # Check if thread has new messages since email_sent_at
        has_reply = gmail_check_thread(campaign.email_thread_id, campaign.email_sent_at)
        if has_reply:
            db.update_campaign(campaign.id, status="responded")
```

---

## 10. Frontend Specification

### 10.1 Pages

**`app/(auth)/outreach/page.tsx`** — CRM Kanban Dashboard

The main view. A drag-and-drop Kanban board with columns for each status.

**Layout:**

```
┌─────────────────────────────────────────────────────────────────────────┐
│  [Drafted (5)]  [Sent (12)]  [Responded (3)]  [Scheduled (1)]  [+]   │
│ ┌──────────┐  ┌──────────┐  ┌──────────┐     ┌──────────┐            │
│ │ Card     │  │ Card     │  │ Card     │     │ Card     │            │
│ │ Acme Co  │  │ Beta Inc │  │ Gamma LLC│     │ Delta Co │            │
│ │ SWE      │  │ PM       │  │ SWE      │     │ MLE      │            │
│ │ ✉ Draft  │  │ ✓ Sent   │  │ 💬 Reply │     │ 📅 Mtg  │            │
│ └──────────┘  └──────────┘  └──────────┘     └──────────┘            │
│ ┌──────────┐  ┌──────────┐                                           │
│ │ Card     │  │ Card     │  [Rejected]       [Archived]              │
│ │ Epsilon  │  │ Zeta     │  (collapsed)      (collapsed)             │
│ └──────────┘  └──────────┘                                           │
└─────────────────────────────────────────────────────────────────────────┘
```

**Card component (`components/crm/CampaignCard.tsx`):**

- Shows: company name, role title, contact name, status badge, date.
- Click to expand: full email preview, contact details, notes, action buttons.
- Drag between columns to update status.

**DnD library:** Use `@dnd-kit/core` + `@dnd-kit/sortable` for accessible drag-and-drop.

```typescript
// On drop:
const handleDragEnd = (event: DragEndEvent) => {
    const { active, over } = event;
    if (!over) return;
    const newStatus = over.id as string;  // Column ID = status
    updateCampaignStatus(active.id as string, newStatus);
};
```

**`app/(auth)/outreach/[id]/page.tsx`** — Campaign Detail

- Full email preview (subject + body) with "Edit" button.
- Contact info section with "Edit" button.
- "Send" button (big, primary) if status is `drafted` and contact_email exists.
- "Regenerate Email" button.
- PDF preview/download link.
- Notes textarea (auto-saves on blur).
- Timeline: creation date, draft date, send date, response date.

### 10.2 Real-time Updates

Subscribe to `outreach_campaigns` via Supabase Realtime:

```typescript
supabase
    .channel('campaigns')
    .on('postgres_changes', {
        event: '*',  // INSERT, UPDATE, DELETE
        schema: 'public',
        table: 'outreach_campaigns',
        filter: `user_id=eq.${userId}`
    }, (payload) => {
        outreachStore.getState().handleRealtimeUpdate(payload);
    })
    .subscribe();
```

This enables: automatic card movement when reply detection fires, real-time count updates in column headers, multi-tab consistency.

### 10.3 OAuth Connection UI

**`app/(auth)/settings/connections/page.tsx`:**

- "Connect Gmail" button → redirects to Google OAuth.
- "Connect Outlook" button → redirects to Microsoft OAuth.
- Status badges: "Connected" (green) / "Not connected" (gray) / "Expired" (red).
- "Disconnect" button for each provider.

### 10.4 Zustand Store

```typescript
interface OutreachStore {
    campaigns: CampaignResponse[];
    counts: Record<string, number>;
    isLoading: boolean;

    fetchCampaigns: (status?: string) => Promise<void>;
    createCampaign: (data: CampaignCreateRequest) => Promise<CampaignResponse>;
    updateStatus: (id: string, status: string) => Promise<void>;
    draftEmail: (id: string, tone?: string) => Promise<EmailDraftResponse>;
    sendEmail: (id: string, provider: string) => Promise<SendResultResponse>;
    handleRealtimeUpdate: (payload: RealtimePayload) => void;
}
```

---

## 11. Testing

### 11.1 Unit Tests

```
tests/unit/test_contact_finder.py      — Title keyword matching, domain extraction
tests/unit/test_email_drafter.py       — _build_prompt(), _parse_email(), _research_company()
tests/unit/test_email_sender.py        — MIME construction, token refresh logic (mocked APIs)
tests/unit/test_oauth_encryption.py    — Encrypt/decrypt roundtrip, expired token handling
tests/unit/test_outreach_schemas.py    — Pydantic validation, email regex
```

### 11.2 Integration Tests

```
tests/integration/test_campaign_api.py  — Full CRUD cycle, status transitions
tests/integration/test_draft_api.py     — Draft endpoint with mocked LLM
tests/integration/test_send_api.py      — Send endpoint with mocked Gmail API
tests/integration/test_kanban_status.py — Verify status transitions are valid (can't go from 'drafted' → 'responded')
```

### 11.3 LLM Output Tests

```
tests/llm/test_email_quality.py — Run draft prompt on 5 fixture scenarios, verify:
                                   - Email is under 150 words
                                   - Contains a "Subject:" line
                                   - Does NOT contain banned phrases ("I hope this finds you",
                                     "synergy", "leverage", "passionate about")
                                   - Contains a clear CTA (question mark present)
                                   - Ends with candidate name
                                   - Does not start with "Dear"
```

---

## 12. Edge Cases & Error Handling

| Scenario | Handling |
|---|---|
| Hunter + Apollo return no contacts | Campaign created with `contact_email = NULL`. UI shows "Contact not found — add manually" prompt. |
| Hunter API key exhausted (rate limit) | Return partial result. Cache failures in Redis to avoid repeated calls. Surface in logs. |
| User hasn't connected Gmail/Outlook | `GET /user/oauth/status` returns false. UI shows "Connect your email" prompt instead of Send button. |
| OAuth token revoked by user externally | Send attempt returns `token_expired`. UI prompts re-authentication. |
| User tries to send without email body | 422 error. UI should disable Send button until email is drafted. |
| User tries to send already-sent campaign | 409 error. UI should show "Already sent" state. |
| Gmail rate limit (per-user sending limit) | `send_failed: rate_limited`. Surface to user: "Gmail is limiting sends — try again in a few minutes." |
| Email bounces | Not detectable in real-time without webhook. Stretch goal: check bounce notifications in next polling cycle. |
| User drags card to invalid status transition | Frontend validates: `drafted → queued/archived`, `queued → sent/drafted`, `sent → responded/rejected/archived`. Backend also validates. |
| Company context search returns nothing | Draft email anyway — the prompt handles missing context by focusing on the role instead of company specifics. |

### 12.1 Valid Status Transitions

```
drafted → queued, archived
queued → sent, drafted (cancel)
sent → responded, meeting_scheduled, rejected, archived
responded → meeting_scheduled, rejected, archived
meeting_scheduled → rejected, archived
rejected → archived
archived → drafted (reactivate)
```

Enforce these in both frontend (disable invalid drop targets) and backend (PATCH validation).

---

## 13. Data Flow

```
Input:     GeneratedApplicationSummary (from Document Assembly)
                │
                ▼
         ┌──────────────┐
         │  CREATE       │  Create campaign row linked to application
         │  CAMPAIGN     │
         └──────┬───────┘
                │
         ┌──────┴───────┐
         │              │
         ▼              ▼
  ┌──────────────┐ ┌──────────────┐
  │  DISCOVER    │ │  RESEARCH    │
  │  CONTACT     │ │  COMPANY     │
  │  (Hunter/    │ │  (web search)│
  │   Apollo)    │ │              │
  └──────┬───────┘ └──────┬───────┘
         │              │
         └──────┬───────┘
                │ contact + company_context
                ▼
         ┌──────────────┐
         │  DRAFT EMAIL  │  Claude Sonnet → subject + body
         └──────┬───────┘
                │ email_subject, email_body
                ▼
         ┌──────────────┐
         │  USER REVIEW  │  Frontend: edit, approve, or regenerate
         └──────┬───────┘
                │ User clicks "Send"
                ▼
         ┌──────────────┐
         │  SEND         │  Gmail/Outlook API via OAuth
         └──────┬───────┘
                │ email_message_id
                ▼
         ┌──────────────┐
         │  TRACK        │  Kanban CRM + reply detection
         └─────────────┘
```

---

*This document is self-contained for building the Outreach CRM module. For shared infrastructure, see `architecture.md`. For the Document Assembly that provides input, see `pipeline-document-assembly.md` (read-only dependency).*
