# Pipeline: Document Assembly & Rendering Engine

> **Prerequisite:** Read `architecture.md` sections 1-3 for platform context, tech stack, and shared conventions.
>
> **Scope:** This document fully specifies the Document Assembly module — the pipeline that takes matched Experience Vault nodes + job requirements, rewrites the bullet points, renders an ATS-friendly PDF, and manages resume caching. An agent with this doc and the architecture doc can build the entire module without consulting any other pipeline doc.
>
> **Owns:** Route group `/generate/*` · Table `generated_applications` · Services `rewriter.py`, `renderer.py` · Tasks `generate_tasks.py` · Prompts `rewrite_resume.py` · Templates `templates/*` · Frontend pages `app/(auth)/generate/*` (status + preview portion)
>
> **Depends on:** Semantic Matcher (provides `MatchResult` with `JobRequirements` + `ExperienceNodeResult[]`). Experience Vault (provides node data via Matcher).
>
> **Consumed by:** Outreach CRM pipeline receives `GeneratedApplicationSummary` from this module.

---

## 1. Purpose

Stitch retrieved experience nodes into a cohesive, tailored, ATS-friendly PDF resume. This is the orchestrator module — it coordinates the Matcher's output into a finished deliverable. It also owns the smart caching system that skips regeneration for similar job descriptions.

---

## 2. Database Schema

### 2.1 `generated_applications` Table

```sql
CREATE TABLE generated_applications (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id             UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    job_description_id  UUID NOT NULL REFERENCES job_descriptions(id),

    -- Generation details
    matched_node_ids    UUID[] NOT NULL DEFAULT '{}',       -- Which vault nodes were selected
    similarity_scores   FLOAT[] NOT NULL DEFAULT '{}',      -- Corresponding cosine similarity scores
    tailored_content    JSONB NOT NULL DEFAULT '{}',        -- The rewritten content per node
    -- tailored_content schema:
    -- {
    --   "nodes": [
    --     {
    --       "node_id": "uuid",
    --       "title": "...",
    --       "organization": "...",
    --       "role": "...",
    --       "start_date": "...",
    --       "end_date": "...",
    --       "bullet_points": ["rewritten bullet 1", "rewritten bullet 2"],
    --       "node_type": "work"
    --     }
    --   ],
    --   "skills_section": ["Python", "C++", "Docker", ...],
    --   "summary": "Tailored professional summary paragraph"
    -- }

    -- Output
    pdf_storage_path    TEXT,                               -- Supabase Storage path: resumes/{user_id}/{id}.pdf
    pdf_url             TEXT,                               -- Signed URL (1-hour expiry, regenerated on access)
    resume_text         TEXT,                               -- Plain text version of the final resume (for email drafter)
    resume_embedding    vector(1536),                       -- Embedding of resume_text for caching

    -- Caching
    cache_hit           BOOLEAN DEFAULT FALSE,
    cache_source_id     UUID REFERENCES generated_applications(id),

    -- Status tracking
    status              TEXT NOT NULL DEFAULT 'pending' CHECK (status IN (
                            'pending', 'scraping', 'extracting', 'matching',
                            'rewriting', 'rendering', 'completed', 'failed'
                        )),
    error_message       TEXT,
    celery_task_id      TEXT,

    created_at          TIMESTAMPTZ DEFAULT NOW(),
    completed_at        TIMESTAMPTZ
);

CREATE INDEX idx_apps_user ON generated_applications(user_id);
CREATE INDEX idx_apps_status ON generated_applications(user_id, status);
CREATE INDEX idx_apps_job ON generated_applications(job_description_id);
CREATE INDEX idx_apps_resume_emb ON generated_applications
    USING hnsw (resume_embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);
```

### 2.2 RLS Policy

```sql
ALTER TABLE generated_applications ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can only access their own applications"
    ON generated_applications FOR ALL
    USING (auth.uid() = user_id)
    WITH CHECK (auth.uid() = user_id);
```

---

## 3. Pydantic Schemas

### 3.1 Request Schemas

```python
# schemas/application.py
class GenerateApplicationRequest(BaseModel):
    job_description_id: UUID  # Must reference an existing, embedded job_descriptions row
    template: str = "modern"  # "modern" | "classic" | "minimal"

class GenerateFromUrlRequest(BaseModel):
    """Convenience endpoint that combines job submission + generation."""
    url: str | None = None
    raw_text: str | None = None
    template: str = "modern"

    def model_post_init(self, __context):
        if not self.url and not self.raw_text:
            raise ValueError("Either url or raw_text must be provided")
```

### 3.2 Response Schemas

```python
class ApplicationStatusResponse(BaseModel):
    id: UUID
    status: str
    error_message: str | None
    cache_hit: bool
    company_name: str | None       # Denormalized from job_descriptions for UI display
    role_title: str | None
    matched_node_count: int        # len(matched_node_ids)
    pdf_url: str | None            # Signed URL, only present when status = 'completed'
    created_at: datetime
    completed_at: datetime | None

class ApplicationDetailResponse(ApplicationStatusResponse):
    matched_nodes: list[dict]      # The tailored_content.nodes array
    similarity_scores: list[float]
    job_requirements: dict         # Denormalized from job_descriptions.requirements

class GeneratedApplicationSummary(BaseModel):
    """Inter-module contract — consumed by Outreach CRM."""
    application_id: UUID
    job_description_id: UUID
    company_name: str | None
    role_title: str | None
    pdf_storage_path: str
    pdf_url: str
    tailored_content: dict
    resume_text_summary: str       # First 500 chars of resume_text for email drafter
```

---

## 4. API Endpoints

Base path: `/generate`

### 4.1 Trigger Generation (from existing job)

```
POST /generate/application
Auth: Required
Body: GenerateApplicationRequest
Returns: 202 + { application_id: UUID, task_id: str }
Side effects: Dispatches generate_application_task
```

**Implementation:**

```python
@router.post("/application", status_code=202)
async def generate_application(body: GenerateApplicationRequest, user_id = Depends(get_current_user)):
    # Verify job exists and is embedded
    job = await db.get_job(body.job_description_id, user_id)
    if not job:
        raise HTTPException(404, "Job description not found")
    if not job.embedding:
        raise HTTPException(409, "Job description not yet processed — try again shortly")

    # Create application row
    app = await db.insert_application(
        user_id=user_id,
        job_description_id=body.job_description_id,
        status="pending",
    )

    # Dispatch orchestrator task
    task = generate_application_task.delay(str(app.id), body.template)
    await db.update_application(app.id, celery_task_id=task.id)

    return {"application_id": app.id, "task_id": task.id}
```

### 4.2 Trigger Generation (from URL — convenience)

```
POST /generate/from-url
Auth: Required
Body: GenerateFromUrlRequest
Returns: 202 + { application_id: UUID, task_id: str }
Side effects: Dispatches full_pipeline_task (scrape → extract → embed → cache check → match → rewrite → render)
```

This is the primary endpoint the frontend uses. It wraps the Matcher and Assembly into one call.

### 4.3 Get Application Status

```
GET /generate/application/{id}
Auth: Required
Returns: 200 + ApplicationStatusResponse
```

**PDF URL refresh:** If `status = 'completed'` and the signed URL is older than 30 minutes, regenerate a fresh signed URL before returning.

### 4.4 Get Application Details

```
GET /generate/application/{id}/details
Auth: Required
Returns: 200 + ApplicationDetailResponse
```

### 4.5 Get PDF Download URL

```
GET /generate/application/{id}/pdf
Auth: Required
Returns: 200 + { url: str } (fresh 1-hour signed URL)
Errors: 404 if not completed
```

### 4.6 List Applications

```
GET /generate/applications?cursor={uuid}&limit={int}
Auth: Required
Returns: 200 + { applications: ApplicationStatusResponse[], cursor: UUID | None }
```

Sorted by `created_at DESC`. Default limit 10, max 50.

---

## 5. The Orchestrator Task

### 5.1 `generate_application_task`

This is the central task that coordinates the entire RAG document generation pipeline. It calls into the Matcher and then does its own rewriting + rendering.

| Property | Value |
|---|---|
| Queue | `heavy` |
| Typical duration | 15-45s |
| Retry policy | 2 retries (but with checkpoint-based resumption) |
| Idempotent | Yes — overwrites all output fields |

```python
@celery_app.task(bind=True, max_retries=2, soft_time_limit=240, time_limit=300)
def generate_application_task(self, application_id: str, template: str = "modern"):
    app = db.get_application(application_id)
    if not app:
        return

    try:
        # ─── STEP 1: GET JOB DATA ───
        job = db.get_job(app.job_description_id)
        if not job or not job.embedding:
            raise TaskError("Job description not ready")

        db.update_application(application_id, status="matching")

        # ─── STEP 2: CACHE CHECK ───
        cache_result = self._check_cache(job.embedding, app.user_id)
        if cache_result:
            db.update_application(application_id,
                status="completed",
                cache_hit=True,
                cache_source_id=cache_result.id,
                matched_node_ids=cache_result.matched_node_ids,
                similarity_scores=cache_result.similarity_scores,
                tailored_content=cache_result.tailored_content,
                pdf_storage_path=cache_result.pdf_storage_path,
                pdf_url=cache_result.pdf_url,
                resume_text=cache_result.resume_text,
                resume_embedding=cache_result.resume_embedding,
                completed_at=datetime.utcnow(),
            )
            return  # Early exit — cache hit

        # ─── STEP 3: VECTOR MATCH ───
        matched_nodes = matcher.find_similar_nodes(
            embedding=job.embedding,
            user_id=app.user_id,
            top_k=5,
        )

        if not matched_nodes:
            raise TaskError("No matching experience nodes found in Vault")

        db.update_application(application_id,
            matched_node_ids=[n.id for n in matched_nodes],
            similarity_scores=[n.similarity_score for n in matched_nodes],
            status="rewriting",
        )

        # ─── STEP 4: REWRITE ───
        job_requirements = JobRequirements(**job.requirements)
        tailored = rewriter.rewrite_nodes(
            nodes=matched_nodes,
            job_requirements=job_requirements,
            user_id=app.user_id,
        )

        db.update_application(application_id,
            tailored_content=tailored,
            status="rendering",
        )

        # ─── STEP 5: RENDER PDF ───
        user_profile = db.get_user_profile(app.user_id)
        pdf_bytes, resume_text = renderer.render_resume(
            profile=user_profile,
            tailored_content=tailored,
            job_requirements=job_requirements,
            template=template,
        )

        # Upload to Supabase Storage
        storage_path = f"resumes/{app.user_id}/{application_id}.pdf"
        storage.upload(storage_path, pdf_bytes, content_type="application/pdf")
        pdf_url = storage.create_signed_url(storage_path, expires_in=3600)

        # ─── STEP 6: EMBED RESUME (for future cache matches) ───
        resume_vector = llm_client.embed(resume_text, user_id=app.user_id)

        db.update_application(application_id,
            pdf_storage_path=storage_path,
            pdf_url=pdf_url,
            resume_text=resume_text,
            resume_embedding=resume_vector,
            status="completed",
            completed_at=datetime.utcnow(),
        )

    except SoftTimeLimitExceeded:
        db.update_application(application_id, status="failed",
            error_message="Generation timed out — please try again")
        raise
    except Exception as e:
        db.update_application(application_id, status="failed",
            error_message=str(e)[:500])
        raise

def _check_cache(self, job_embedding: list[float], user_id: UUID):
    """Find a previously generated application with similar enough job description."""
    threshold = float(settings.CACHE_SIMILARITY_THRESHOLD)  # Default 0.88

    query = """
        SELECT * FROM generated_applications
        WHERE user_id = $1
          AND status = 'completed'
          AND resume_embedding IS NOT NULL
          AND 1 - (resume_embedding <=> $2::vector) > $3
        ORDER BY 1 - (resume_embedding <=> $2::vector) DESC
        LIMIT 1;
    """
    return db.fetch_one(query, [user_id, job_embedding, threshold])
```

### 5.2 `full_pipeline_task`

For the `/generate/from-url` convenience endpoint. Wraps Matcher scraping + extraction + embedding, then calls `generate_application_task` logic.

```python
@celery_app.task(bind=True, max_retries=1, soft_time_limit=240, time_limit=300)
def full_pipeline_task(self, application_id: str, url: str = None, raw_text: str = None, template: str = "modern"):
    app = db.get_application(application_id)

    try:
        # ─── SCRAPE (if URL) ───
        db.update_application(application_id, status="scraping")
        if url:
            cached_text = redis.get(f"scrape:{url}")
            if cached_text:
                raw_text = cached_text
            else:
                result = scraper.scrape(url)
                raw_text = result.raw_text
                redis.setex(f"scrape:{url}", 3600, raw_text)

        # ─── INSERT JOB ───
        db.update_application(application_id, status="extracting")
        job = db.insert_job(user_id=app.user_id, url=url, raw_text=raw_text)

        # ─── EXTRACT REQUIREMENTS ───
        requirements_json = llm_client.complete(
            system_prompt=EXTRACT_REQUIREMENTS_SYSTEM_PROMPT,
            user_prompt=raw_text,
            model="claude-sonnet-4-20250514",
            response_format="json",
            user_id=app.user_id,
            task_type="extract",
        )
        requirements = JobRequirements(**json.loads(requirements_json))
        embedding_text = build_job_embedding_text(requirements)
        job_embedding = llm_client.embed(embedding_text, user_id=app.user_id)

        db.update_job(job.id,
            company_name=requirements.company_name,
            role_title=requirements.role_title,
            requirements=requirements.model_dump(),
            embedding=job_embedding,
        )
        db.update_application(application_id, job_description_id=job.id)

        # ─── HAND OFF TO GENERATE LOGIC (Steps 2-6 from generate_application_task) ───
        # ... (identical logic: cache check → match → rewrite → render → embed)

    except Exception as e:
        db.update_application(application_id, status="failed", error_message=str(e)[:500])
        raise
```

---

## 6. Services

### 6.1 Rewriter Service (`services/rewriter.py`)

```python
class ResumeRewriter:
    def rewrite_nodes(
        self,
        nodes: list[ExperienceNodeResult],
        job_requirements: JobRequirements,
        user_id: UUID,
    ) -> dict:
        """Rewrite node bullet points to align with job requirements."""

        # Build the LLM input
        nodes_json = [
            {
                "node_id": str(n.id),
                "title": n.title,
                "organization": n.organization,
                "role": n.role,
                "start_date": str(n.start_date) if n.start_date else None,
                "end_date": str(n.end_date) if n.end_date else None,
                "bullet_points": n.bullet_points,
                "node_type": n.node_type,
            }
            for n in nodes
        ]

        job_summary = self._build_job_summary(job_requirements)

        response = llm_client.complete(
            system_prompt=REWRITE_SYSTEM_PROMPT,
            user_prompt=f"TARGET JOB:\n{job_summary}\n\nEXPERIENCE NODES:\n{json.dumps(nodes_json, indent=2)}",
            model="claude-sonnet-4-20250514",
            response_format="json",
            user_id=user_id,
            task_type="rewrite",
            prompt_version=REWRITE_VERSION,
        )

        result = json.loads(response)

        # Validation: ensure every original node is present
        original_ids = {str(n.id) for n in nodes}
        returned_ids = {n["node_id"] for n in result["nodes"]}
        if original_ids != returned_ids:
            raise ValueError("Rewriter dropped or added nodes — aborting")

        # Generate skills section from job requirements + node tags
        all_tags = set()
        for n in nodes:
            all_tags.update(n.tags)
        relevant_skills = [s for s in job_requirements.technical_skills if s.lower() in
                          {t.lower() for t in all_tags}]
        # Add remaining user skills not in JD but still valuable
        remaining = [t for t in all_tags if t.lower() not in
                    {s.lower() for s in relevant_skills}][:5]
        result["skills_section"] = relevant_skills + remaining

        return result

    def _build_job_summary(self, req: JobRequirements) -> str:
        parts = []
        if req.role_title:
            parts.append(f"Role: {req.role_title}")
        if req.company_name:
            parts.append(f"Company: {req.company_name}")
        if req.technical_skills:
            parts.append(f"Technical requirements: {', '.join(req.technical_skills)}")
        if req.responsibilities:
            parts.append(f"Key responsibilities: {'; '.join(req.responsibilities[:5])}")
        if req.experience_years:
            parts.append(f"Experience: {req.experience_years}+ years")
        return "\n".join(parts)
```

### 6.2 Renderer Service (`services/renderer.py`)

```python
from weasyprint import HTML
from jinja2 import Environment, FileSystemLoader

class ResumeRenderer:
    def __init__(self):
        self.jinja_env = Environment(
            loader=FileSystemLoader("app/templates/"),
            autoescape=True,
        )

    def render_resume(
        self,
        profile: UserProfile,
        tailored_content: dict,
        job_requirements: JobRequirements,
        template: str = "modern",
    ) -> tuple[bytes, str]:
        """Returns (pdf_bytes, plain_text_resume)."""

        # Load template
        html_template = self.jinja_env.get_template(f"{template}.html")

        # Build template context
        context = {
            "name": profile.full_name,
            "email": profile.email,
            "phone": profile.phone,
            "location": profile.location,
            "linkedin": profile.linkedin_url,
            "github": profile.github_url,
            "portfolio": profile.portfolio_url,
            "headline": profile.headline,
            "summary": tailored_content.get("summary", ""),
            "skills": tailored_content.get("skills_section", []),
            "experiences": self._sort_experiences(tailored_content["nodes"]),
            "target_role": job_requirements.role_title,
        }

        # Render HTML
        html_string = html_template.render(**context)

        # Generate PDF
        pdf_bytes = HTML(string=html_string).write_pdf()

        # Generate plain text (for embedding + email drafter)
        plain_text = self._html_to_plain_text(context)

        return pdf_bytes, plain_text

    def _sort_experiences(self, nodes: list[dict]) -> list[dict]:
        """Sort by end_date DESC (ongoing first), then start_date DESC."""
        def sort_key(n):
            end = n.get("end_date") or "9999-99"  # Ongoing = top
            start = n.get("start_date") or "0000-00"
            return (end, start)
        return sorted(nodes, key=sort_key, reverse=True)

    def _html_to_plain_text(self, context: dict) -> str:
        """Build a plain text version for embedding and email drafter context."""
        lines = [context["name"]]
        if context.get("headline"):
            lines.append(context["headline"])
        lines.append("")
        if context.get("summary"):
            lines.append(context["summary"])
            lines.append("")
        for exp in context["experiences"]:
            header = exp["title"]
            if exp.get("organization"):
                header += f" at {exp['organization']}"
            if exp.get("role"):
                header += f" — {exp['role']}"
            lines.append(header)
            for bp in exp["bullet_points"]:
                lines.append(f"  • {bp}")
            lines.append("")
        if context.get("skills"):
            lines.append("Skills: " + ", ".join(context["skills"]))
        return "\n".join(lines)
```

---

## 7. Resume Templates

### 7.1 ATS Compliance Rules (All Templates)

Every template must follow these rules for Applicant Tracking System compatibility:

- Use semantic HTML: `<h1>` for name, `<h2>` for section headers, `<p>`, `<ul>`, `<li>`.
- **No tables for layout.** Tables confuse ATS parsers.
- **No images, icons, or graphics** in the body.
- **No multi-column layouts.** Single column, left-aligned.
- Web-safe fonts only: Arial, Helvetica, Georgia, Times New Roman.
- Section headers must be `<h2>` tags for ATS heading detection.
- No critical info in headers/footers (some ATS skip them).
- Use `@page { margin: 1in; }` for consistent print margins.
- Max 2 pages. Template should handle overflow gracefully.

### 7.2 Template: `modern.html`

```html
<!DOCTYPE html>
<html>
<head>
<style>
    @page { size: letter; margin: 0.75in 1in; }
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body { font-family: Arial, Helvetica, sans-serif; font-size: 10.5pt; line-height: 1.4; color: #333; }
    h1 { font-size: 18pt; color: #1a1a1a; margin-bottom: 2pt; }
    .contact { font-size: 9pt; color: #555; margin-bottom: 12pt; }
    .contact a { color: #555; text-decoration: none; }
    h2 { font-size: 12pt; color: #2c5282; border-bottom: 1px solid #2c5282;
         padding-bottom: 2pt; margin: 14pt 0 6pt 0; text-transform: uppercase;
         letter-spacing: 0.5pt; }
    .experience-header { display: flex; justify-content: space-between; margin-bottom: 2pt; }
    .experience-title { font-weight: bold; font-size: 10.5pt; }
    .experience-dates { font-size: 9.5pt; color: #555; }
    .experience-org { font-size: 10pt; color: #444; font-style: italic; margin-bottom: 4pt; }
    ul { padding-left: 18pt; margin-bottom: 8pt; }
    li { margin-bottom: 2pt; font-size: 10pt; }
    .skills { font-size: 10pt; }
    .summary { font-size: 10pt; margin-bottom: 8pt; color: #444; }
</style>
</head>
<body>
    <h1>{{ name }}</h1>
    <div class="contact">
        {{ email }}
        {% if phone %} · {{ phone }}{% endif %}
        {% if location %} · {{ location }}{% endif %}
        {% if linkedin %} · <a href="{{ linkedin }}">LinkedIn</a>{% endif %}
        {% if github %} · <a href="{{ github }}">GitHub</a>{% endif %}
        {% if portfolio %} · <a href="{{ portfolio }}">Portfolio</a>{% endif %}
    </div>

    {% if summary %}
    <p class="summary">{{ summary }}</p>
    {% endif %}

    {% if skills %}
    <h2>Technical Skills</h2>
    <p class="skills">{{ skills | join(', ') }}</p>
    {% endif %}

    <h2>Experience</h2>
    {% for exp in experiences %}
    <div class="experience-header">
        <span class="experience-title">{{ exp.title }}{% if exp.role %} — {{ exp.role }}{% endif %}</span>
        <span class="experience-dates">
            {% if exp.start_date %}{{ exp.start_date }}{% endif %}
            {% if exp.start_date and exp.end_date %} – {% endif %}
            {{ exp.end_date or 'Present' }}
        </span>
    </div>
    {% if exp.organization %}
    <div class="experience-org">{{ exp.organization }}</div>
    {% endif %}
    <ul>
        {% for bp in exp.bullet_points %}
        <li>{{ bp }}</li>
        {% endfor %}
    </ul>
    {% endfor %}
</body>
</html>
```

### 7.3 Additional Templates

Maintain at least `modern.html` (above), `classic.html` (Times New Roman, more traditional), and `minimal.html` (maximum whitespace, minimal color). All must follow the ATS rules. CSS is inline within each template (WeasyPrint requires it).

---

## 8. LLM Prompts

### 8.1 `rewrite_resume.py`

```python
VERSION = "rewrite_v1"

SYSTEM_PROMPT = """You are a professional resume writer. You will be given a set of experience
entries and a target job description. Your job is to subtly tailor the phrasing of each
bullet point to align with the language and priorities of the job description.

Return ONLY a JSON object with this structure. No explanation, no markdown fences.

{
  "nodes": [
    {
      "node_id": "original-uuid",
      "title": "original title",
      "organization": "original org",
      "role": "original role",
      "start_date": "original date",
      "end_date": "original date or null",
      "bullet_points": ["rewritten bullet 1", "rewritten bullet 2", ...],
      "node_type": "original type"
    }
  ],
  "summary": "A 2-3 sentence professional summary tailored to the target role."
}

RULES:
1. You MUST NOT invent new skills, experiences, or achievements.
2. You MUST NOT change the factual substance of any bullet point.
3. You MAY reorder bullet points within a node to prioritize relevance to the target role.
4. You MAY adjust verb choices and phrasing to mirror the job description's terminology.
   Example: if JD says "cross-functional collaboration", adjust "worked with other teams"
   to "drove cross-functional collaboration across engineering and product."
5. You MUST preserve ALL quantitative claims exactly as stated (percentages, dollar amounts,
   team sizes, timelines). Do not round, inflate, or modify numbers.
6. Each bullet point should start with a strong past-tense action verb.
7. Limit each node to 3-5 bullet points. If the original has more, select the most relevant.
8. The "summary" field should be a compelling 2-3 sentence professional summary that
   positions the candidate for the target role without being generic.
9. Preserve all node_id values exactly — they are used for validation.
10. Include ALL nodes from the input — do not drop any."""
```

---

## 9. Smart Caching System

### 9.1 How It Works

Before generating a new resume, the orchestrator checks whether a sufficiently similar resume already exists.

**Similarity target:** The cache compares the **new job description's embedding** against **existing resume embeddings** (`generated_applications.resume_embedding`). This catches cases where two different job postings describe essentially the same role.

**Threshold:** `CACHE_SIMILARITY_THRESHOLD` env var, default `0.88`. Only near-identical job descriptions trigger a cache hit.

**Cache invalidation:** When a user updates or adds Experience Vault nodes, existing cache entries remain valid because the cached resume was the best-fit *at the time*. A manual "Regenerate" button in the UI allows the user to bypass cache for a specific application.

### 9.2 Cache-Busting Endpoint

```
POST /generate/application/{id}/regenerate
Auth: Required
Returns: 202 + { application_id: UUID, task_id: str }
Action: Creates a new application row linked to the same job_description_id,
        with cache checking DISABLED. Dispatches generate_application_task.
```

---

## 10. Frontend Specification

### 10.1 Pages

**`app/(auth)/generate/page.tsx`** — Main generation page

This page combines the Matcher's job input with this module's generation status.

Layout:
1. **Top section:** Job input (owned by Semantic Matcher — `JobInput` component).
2. **Middle section:** Generation status (owned by this module).
3. **Bottom section:** Application history list.

**Generation status component (`components/generate/GenerationStatus.tsx`):**

- Shows a multi-step progress indicator: `Scraping → Extracting → Matching → Rewriting → Rendering → Complete`
- Each step lights up as the `status` field progresses.
- Poll `GET /generate/application/{id}` every 3 seconds, OR subscribe via Supabase Realtime.
- On `completed`: show PDF preview (embedded via `<iframe>` or PDF.js) + "Download" button + "Send to Hiring Manager" button (links to Outreach CRM).
- On `failed`: show error message + "Try Again" button.
- On `cache_hit`: show a badge "Served from cache — a similar resume was generated previously" + "Regenerate" button.

**`app/(auth)/generate/history/page.tsx`** — Past applications

- List of all `generated_applications` for the user, sorted by date.
- Each row: company name, role title, date, status badge, "View PDF" link.
- Click through to detail view showing matched nodes and similarity scores.

### 10.2 Zustand Store

```typescript
interface GenerateStore {
    currentApplication: ApplicationStatusResponse | null;
    applications: ApplicationStatusResponse[];
    isGenerating: boolean;

    generateFromUrl: (url: string, template?: string) => Promise<void>;
    generateFromText: (text: string, template?: string) => Promise<void>;
    pollStatus: (id: string) => Promise<void>;
    fetchApplications: () => Promise<void>;
    regenerate: (id: string) => Promise<void>;
}
```

---

## 11. Testing

### 11.1 Unit Tests

```
tests/unit/test_rewriter.py           — build_job_summary(), node validation logic
tests/unit/test_renderer.py           — _sort_experiences(), _html_to_plain_text()
tests/unit/test_cache_check.py        — Cache threshold logic with mock similarity scores
tests/unit/test_application_schemas.py — Pydantic validation
```

### 11.2 Integration Tests

```
tests/integration/test_generate_api.py    — Full generation flow with mocked LLM + storage
tests/integration/test_cache_hit.py       — Generate twice with similar jobs, verify cache hit
tests/integration/test_pdf_rendering.py   — Render a template with fixture data, verify PDF is valid
```

### 11.3 LLM Output Tests

```
tests/llm/test_rewrite_quality.py     — Run rewrite prompt on 3 fixture node sets + JDs, verify:
                                         - Returns valid JSON matching expected schema
                                         - All original node_ids present
                                         - No new node_ids invented
                                         - All quantitative claims preserved exactly
                                         - Bullet points start with action verbs
                                         - Summary is 2-3 sentences
```

### 11.4 Template Visual Tests

- Render each template with a fixture data set and inspect the PDF manually.
- Verify: single column, no images, semantic headings, readable at 10pt, fits on 1-2 pages.
- Run the PDF through an ATS simulator (e.g., Jobscan) to verify parse-ability.

---

## 12. Edge Cases & Error Handling

| Scenario | Handling |
|---|---|
| Job has 0 matching nodes (empty Vault or no overlap) | Fail with message "No matching experience found — add more nodes to your Vault." |
| Rewriter LLM drops a node from the output | Validation check catches this. Retry once. If still fails, use original (unrewritten) bullet points for the dropped node. |
| Rewriter LLM invents a new node_id | Validation check catches this. Strip the invented node, proceed with valid ones. |
| Rewriter LLM changes a number (e.g., "40%" → "45%") | This is the hardest to detect automatically. LLM output tests should catch regressions in prompt quality. Log a diff for audit. |
| WeasyPrint fails to render | Fail with generic error. Log the HTML string for debugging. Common cause: invalid CSS or missing fonts. |
| PDF exceeds 3 pages | The template should have CSS `@page` rules and content should be capped at 5 nodes × 4 bullets. If still too long, truncate to 4 nodes. |
| Supabase Storage upload fails | Retry once. If still fails, fail the task. The rewritten content is preserved in `tailored_content` so the user doesn't lose work. |
| User clicks "Regenerate" while a generation is in progress | Create a new application row. The old one will complete or fail independently. |
| Signed URL expires before user downloads | The `GET /generate/application/{id}/pdf` endpoint always generates a fresh URL. |

---

## 13. Data Flow

```
Input:     job_description_id (from Matcher, already embedded)
                │
                ▼
         ┌──────────────┐
         │  CACHE CHECK  │  Compare job embedding vs existing resume embeddings
         │  (threshold   │  If hit → return cached PDF, skip everything below
         │   0.88)       │
         └──────┬───────┘
                │ No cache hit
                ▼
         ┌──────────────┐
         │  MATCH        │  pgvector query → top 5 ExperienceNodeResult[]
         └──────┬───────┘
                │
                ▼
         ┌──────────────┐
         │  REWRITE      │  Claude Sonnet → tailored bullet points + summary
         └──────┬───────┘
                │ tailored_content JSON
                ▼
         ┌──────────────┐
         │  RENDER       │  Jinja2 + WeasyPrint → PDF bytes
         └──────┬───────┘
                │
                ▼
         ┌──────────────┐
         │  UPLOAD       │  Supabase Storage → signed URL
         └──────┬───────┘
                │
                ▼
         ┌──────────────┐
         │  EMBED RESUME │  text-embedding-3-small → vector (for future cache)
         └──────┬───────┘
                │
                ▼
Output:    GeneratedApplicationSummary
           → Consumed by Outreach CRM pipeline
```

---

*This document is self-contained for building the Document Assembly & Rendering module. For shared infrastructure, see `architecture.md`. For the Matcher that provides input, see `pipeline-semantic-matcher.md` (read-only dependency).*
