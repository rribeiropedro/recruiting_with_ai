# Pipeline: Semantic Matcher (Job Analysis)

> **Prerequisite:** Read `architecture.md` sections 1-3 for platform context, tech stack, and shared conventions.
>
> **Scope:** This document fully specifies the Semantic Matcher module — the pipeline that scrapes a job description, extracts structured requirements, embeds them, and retrieves the best-matching Experience Vault nodes. An agent with this doc and the architecture doc can build the entire Matcher without consulting any other pipeline doc.
>
> **Owns:** Route group `/jobs/*` · Table `job_descriptions` · Services `scraper.py`, `matcher.py` · Tasks `scrape_tasks.py` (job scraping) · Prompts `extract_requirements.py` · Frontend pages `app/(auth)/generate/page.tsx` (job input portion only)
>
> **Depends on:** `experience_nodes` table (read-only, via vector similarity query). Does NOT write to `experience_nodes`.
>
> **Consumed by:** Document Assembly pipeline receives `JobRequirements` + `ExperienceNodeResult[]` from this module.

---

## 1. Purpose

Translate an employer's job description into a mathematical query against the Experience Vault. This module is the bridge between "here's a job URL" and "here are your 5 most relevant experience nodes."

The pipeline has three stages: **Scrape → Extract → Match**.

---

## 2. Database Schema

### 2.1 `job_descriptions` Table

```sql
CREATE TABLE job_descriptions (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id             UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,

    -- Source
    url                 TEXT,                                -- Original job URL (NULL if pasted)
    raw_html            TEXT,                                -- Preserved for debugging
    raw_text            TEXT NOT NULL,                       -- Cleaned extracted text

    -- Parsed (LLM-extracted)
    company_name        TEXT,
    role_title          TEXT,
    requirements        JSONB NOT NULL DEFAULT '{}',         -- Structured JobRequirements JSON
    -- Schema:
    -- {
    --   "technical_skills": ["Python", "SQL", ...],
    --   "soft_skills": ["communication", ...],
    --   "responsibilities": ["Design...", "Lead..."],
    --   "experience_years": 3,
    --   "education": "BS in CS or equivalent",
    --   "nice_to_haves": ["Kubernetes", ...],
    --   "industry": "fintech"
    -- }

    -- Matching
    embedding           vector(1536),                        -- Embedding of the requirements text

    -- Housekeeping
    scraped_at          TIMESTAMPTZ,                         -- NULL if manually pasted
    created_at          TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_jobs_user ON job_descriptions(user_id);
CREATE INDEX idx_jobs_embedding ON job_descriptions
    USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);
CREATE INDEX idx_jobs_url ON job_descriptions(user_id, url);
```

### 2.2 RLS Policy

```sql
ALTER TABLE job_descriptions ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can only access their own jobs"
    ON job_descriptions FOR ALL
    USING (auth.uid() = user_id)
    WITH CHECK (auth.uid() = user_id);
```

---

## 3. Pydantic Schemas

### 3.1 Request Schemas

```python
# schemas/job.py
from pydantic import BaseModel, Field, field_validator
import re

class JobSubmitRequest(BaseModel):
    url: str | None = None
    raw_text: str | None = None

    @field_validator("url")
    @classmethod
    def validate_url(cls, v):
        if v and not re.match(r"^https://", v):
            raise ValueError("URL must use HTTPS")
        return v

    def model_post_init(self, __context):
        if not self.url and not self.raw_text:
            raise ValueError("Either url or raw_text must be provided")
```

### 3.2 Response Schemas

```python
class JobRequirements(BaseModel):
    """Inter-module contract — consumed by Document Assembly."""
    company_name: str | None = None
    role_title: str | None = None
    technical_skills: list[str] = []
    soft_skills: list[str] = []
    responsibilities: list[str] = []
    experience_years: int | None = None
    education: str | None = None
    nice_to_haves: list[str] = []
    industry: str | None = None

class JobDescriptionResponse(BaseModel):
    id: UUID
    url: str | None
    company_name: str | None
    role_title: str | None
    requirements: JobRequirements
    is_embedded: bool  # Computed: embedding IS NOT NULL
    created_at: datetime

class MatchResult(BaseModel):
    """Returned by the match endpoint — consumed by Document Assembly."""
    job_description_id: UUID
    job_requirements: JobRequirements
    matched_nodes: list[ExperienceNodeResult]  # From architecture.md contract
    low_relevance_warning: bool  # True if top similarity < 0.3
```

---

## 4. API Endpoints

Base path: `/jobs`

### 4.1 Submit Job Description

```
POST /jobs/submit
Auth: Required
Body: JobSubmitRequest
Returns: 201 + JobDescriptionResponse
Side effects: If URL provided, dispatches scrape_job_task.
              If raw_text provided, dispatches extract_and_embed_task immediately.
```

**Implementation:**

```python
@router.post("/submit", status_code=201)
async def submit_job(body: JobSubmitRequest, user_id: UUID = Depends(get_current_user)):
    if body.url:
        # Check scrape cache first
        cached = await redis.get(f"scrape:{body.url}")
        if cached:
            raw_text = cached
        else:
            # Insert placeholder row
            job = await db.insert_job(user_id=user_id, url=body.url, raw_text="")
            # Dispatch scrape → extract → embed as a chain
            scrape_job_task.delay(str(job.id))
            return JobDescriptionResponse.from_orm(job)

    # Direct text input — skip scraping
    job = await db.insert_job(user_id=user_id, raw_text=body.raw_text)
    extract_and_embed_task.delay(str(job.id))
    return JobDescriptionResponse.from_orm(job)
```

### 4.2 Get Job Description

```
GET /jobs/{id}
Auth: Required
Returns: 200 + JobDescriptionResponse
```

### 4.3 Match Job Against Vault

```
POST /jobs/{id}/match
Auth: Required
Returns: 200 + MatchResult
Requires: Job must have embedding (is_embedded = true)
Errors: 409 if embedding not yet ready
```

**This endpoint is called by the Document Assembly orchestrator task**, not typically by the frontend directly. It can also be called standalone for preview purposes.

**Implementation:**

```python
@router.post("/{job_id}/match")
async def match_job(job_id: UUID, user_id: UUID = Depends(get_current_user)):
    job = await db.get_job(job_id, user_id)
    if not job or not job.embedding:
        raise HTTPException(409, "Job description not yet processed")

    matched_nodes = await matcher.find_similar_nodes(
        embedding=job.embedding,
        user_id=user_id,
        top_k=5
    )

    low_relevance = len(matched_nodes) == 0 or matched_nodes[0].similarity_score < 0.3

    return MatchResult(
        job_description_id=job.id,
        job_requirements=JobRequirements(**job.requirements),
        matched_nodes=matched_nodes,
        low_relevance_warning=low_relevance,
    )
```

---

## 5. Services

### 5.1 Scraper Service (`services/scraper.py`)

Two-tier scraping with automatic fallback:

```python
class JobScraper:
    async def scrape(self, url: str) -> ScrapeResult:
        """Returns ScrapeResult(raw_html, raw_text, method)."""

        # Tier 1: Fast path — lightweight HTTP GET
        result = await self._fast_scrape(url)
        if result and len(result.raw_text.split()) > 200:
            return result

        # Tier 2: Slow path — headless browser
        result = await self._playwright_scrape(url)
        if result and len(result.raw_text.split()) > 50:
            return result

        raise ScrapeError(f"Could not extract job description from {url}")

    async def _fast_scrape(self, url: str) -> ScrapeResult | None:
        """httpx + BeautifulSoup for static pages."""
        try:
            async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
                response = await client.get(url, headers={"User-Agent": REALISTIC_USER_AGENT})
                response.raise_for_status()

            soup = BeautifulSoup(response.text, "html.parser")

            # Remove noise elements
            for tag in soup.find_all(["nav", "footer", "header", "script", "style",
                                       "aside", "iframe"]):
                tag.decompose()

            # Try common job description containers
            text = self._extract_job_text(soup)
            return ScrapeResult(raw_html=response.text, raw_text=text, method="httpx")
        except Exception:
            return None

    async def _playwright_scrape(self, url: str) -> ScrapeResult | None:
        """Headless Chromium for JS-rendered pages."""
        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                context = await browser.new_context(
                    user_agent=REALISTIC_USER_AGENT,
                    viewport={"width": 1280, "height": 800},
                )
                page = await context.new_page()

                # Disable navigator.webdriver detection
                await page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

                await page.goto(url, wait_until="networkidle", timeout=30000)
                await page.wait_for_timeout(random.randint(1000, 3000))  # Random delay

                html = await page.content()
                text = await page.inner_text("body")
                await browser.close()

            # Clean the text
            text = self._clean_text(text)
            return ScrapeResult(raw_html=html, raw_text=text, method="playwright")
        except Exception:
            return None

    def _extract_job_text(self, soup: BeautifulSoup) -> str:
        """Try common job page selectors, fall back to body text."""
        selectors = [
            "[data-testid='jobDescription']",
            ".job-description",
            "#job-description",
            "[class*='description']",
            "article",
            "main",
        ]
        for sel in selectors:
            el = soup.select_one(sel)
            if el and len(el.get_text(strip=True)) > 100:
                return self._clean_text(el.get_text(separator="\n", strip=True))
        return self._clean_text(soup.get_text(separator="\n", strip=True))

    def _clean_text(self, text: str) -> str:
        """Normalize whitespace, remove cookie banners, etc."""
        lines = [line.strip() for line in text.split("\n") if line.strip()]
        # Remove short noise lines (cookie notices, nav items)
        lines = [line for line in lines if len(line) > 20 or any(
            kw in line.lower() for kw in ["requirement", "qualif", "responsib", "experience"]
        )]
        return "\n".join(lines)
```

**CAPTCHA handling:** If Playwright encounters a CAPTCHA page (heuristic: page contains "verify you are human" or "captcha" and has <200 words of job content), raise `ScrapeError("CAPTCHA detected — please paste the job description manually")`.

**Scrape caching:** After a successful scrape, cache `raw_text` in Redis with key `scrape:{url}` and TTL of 1 hour.

### 5.2 Matcher Service (`services/matcher.py`)

```python
class SemanticMatcher:
    async def find_similar_nodes(
        self,
        embedding: list[float],
        user_id: UUID,
        top_k: int = 5,
    ) -> list[ExperienceNodeResult]:
        """Execute vector similarity search against the Experience Vault."""
        query = """
            SELECT
                id, title, organization, role, start_date, end_date,
                description, bullet_points, node_type, tags,
                1 - (embedding <=> $1::vector) AS similarity_score
            FROM experience_nodes
            WHERE user_id = $2
              AND is_archived = FALSE
              AND embedding IS NOT NULL
            ORDER BY embedding <=> $1::vector
            LIMIT $3;
        """
        rows = await db.fetch_all(query, [embedding, user_id, top_k])
        return [ExperienceNodeResult(**row) for row in rows]
```

---

## 6. Background Tasks

### 6.1 `scrape_job_task`

| Property | Value |
|---|---|
| Queue | `heavy` |
| Typical duration | 5-30s (Playwright path) |
| Retry policy | 2 retries, delays: 10s, 30s |
| Idempotent | Yes — overwrites `raw_text`, `raw_html` |

**Logic:**

```python
@celery_app.task(bind=True, max_retries=2)
def scrape_job_task(self, job_id: str):
    job = db.get_job(job_id)
    if not job or not job.url:
        return

    try:
        result = scraper.scrape(job.url)  # Sync wrapper around async scrape
    except ScrapeError as e:
        db.update_job(job_id, raw_text=str(e))
        raise

    db.update_job(job_id,
        raw_text=result.raw_text,
        raw_html=result.raw_html,
        scraped_at=datetime.utcnow()
    )

    # Cache for 1 hour
    redis.setex(f"scrape:{job.url}", 3600, result.raw_text)

    # Chain into extraction + embedding
    extract_and_embed_task.delay(job_id)
```

### 6.2 `extract_and_embed_task`

| Property | Value |
|---|---|
| Queue | `default` |
| Typical duration | 5-10s |
| Retry policy | 2 retries, delays: 5s, 15s |
| Idempotent | Yes — overwrites `requirements`, `embedding` |

**Logic:**

```python
@celery_app.task(bind=True, max_retries=2)
def extract_and_embed_task(self, job_id: str):
    job = db.get_job(job_id)
    if not job or not job.raw_text:
        return

    # Step 1: Extract requirements via LLM
    requirements_json = llm_client.complete(
        system_prompt=EXTRACT_REQUIREMENTS_SYSTEM_PROMPT,
        user_prompt=job.raw_text,
        model="claude-sonnet-4-20250514",
        response_format="json",
        user_id=job.user_id,
        task_type="extract",
        prompt_version=EXTRACT_REQUIREMENTS_VERSION,
    )

    try:
        requirements = JobRequirements(**json.loads(requirements_json))
    except (json.JSONDecodeError, ValidationError):
        if self.request.retries < 1:
            raise self.retry(countdown=5)
        raise

    # Step 2: Build embedding text from extracted requirements
    embedding_text = build_job_embedding_text(requirements)
    vector = llm_client.embed(embedding_text, user_id=job.user_id)

    # Step 3: Update DB
    db.update_job(job_id,
        company_name=requirements.company_name,
        role_title=requirements.role_title,
        requirements=requirements.model_dump(),
        embedding=vector,
    )
```

**Embedding text construction for jobs:**

```python
def build_job_embedding_text(req: JobRequirements) -> str:
    parts = []
    if req.role_title:
        parts.append(req.role_title)
    parts.extend(req.technical_skills)
    parts.extend(req.responsibilities[:5])  # Cap to avoid overly long embedding inputs
    if req.education:
        parts.append(req.education)
    parts.extend(req.nice_to_haves[:3])
    return " | ".join(parts)
```

---

## 7. LLM Prompts

### 7.1 `extract_requirements.py`

```python
VERSION = "extract_v1"

SYSTEM_PROMPT = """You are a job description analyzer. Given the raw text of a job posting,
extract structured requirements.

Return ONLY a JSON object with these exact fields. No explanation, no markdown fences.

{
  "company_name": "string or null",
  "role_title": "string or null",
  "technical_skills": ["string", ...],
  "soft_skills": ["string", ...],
  "responsibilities": ["string", ...],
  "experience_years": number or null,
  "education": "string or null",
  "nice_to_haves": ["string", ...],
  "industry": "string or null"
}

Rules:
- technical_skills: Programming languages, frameworks, tools, platforms explicitly mentioned
  as required. Include version numbers if specified (e.g., "Python 3.10+").
- soft_skills: Communication, leadership, teamwork, etc. Only include if explicitly stated.
- responsibilities: Key duties and deliverables. Summarize, don't copy verbatim.
  Limit to 5-8 items.
- experience_years: Extract the number if stated (e.g., "3+ years" → 3). null if not mentioned.
- education: Degree requirement as stated (e.g., "BS in Computer Science or equivalent").
- nice_to_haves: Skills listed as "preferred", "bonus", or "nice to have".
- industry: The sector this company operates in (e.g., "fintech", "healthcare", "SaaS").
- company_name and role_title: Extract from the posting header/title.

If a field cannot be determined from the text, use null or an empty array.
Do NOT infer requirements that are not explicitly stated or strongly implied."""
```

---

## 8. Frontend Specification

The Matcher's frontend is the **job input portion** of the generate page. The full generate page is shared with Document Assembly, but the input portion is owned by this module.

### 8.1 Job Input Component

**`components/vault/JobInput.tsx`** (or `components/generate/JobInput.tsx`)

- Two-tab input:
  - **URL tab:** Single text input for job URL. "Analyze" button.
  - **Paste tab:** Large textarea for raw job description text. "Analyze" button.
- On submit: `POST /jobs/submit`. Show loading spinner.
- When job is processed (`is_embedded = true`): display the extracted `company_name`, `role_title`, and a tag list of `technical_skills`. Show a "Generate Resume" button that triggers Document Assembly.
- If scraping fails: show error message and auto-switch to the Paste tab.

### 8.2 Low Relevance Warning

If `MatchResult.low_relevance_warning` is true, display a yellow warning banner: "Your Experience Vault may not contain directly relevant experience for this role. The generated resume will use your closest matches, but consider adding more relevant nodes to your Vault."

---

## 9. Testing

### 9.1 Unit Tests

```
tests/unit/test_scraper.py            — Test _clean_text(), _extract_job_text() with HTML fixtures
tests/unit/test_matcher.py            — Test build_job_embedding_text() with various JobRequirements
tests/unit/test_job_schemas.py        — Pydantic validation: URL format, mutual exclusivity
```

### 9.2 Integration Tests

```
tests/integration/test_job_api.py     — Submit URL, verify job row created and task dispatched
tests/integration/test_job_match.py   — Insert pre-embedded job + nodes, verify match returns correct top-k
tests/integration/test_scrape_cache.py — Scrape same URL twice, verify second is cached
```

### 9.3 LLM Output Tests

```
tests/llm/test_extract_requirements.py — Run extract prompt on 5 fixture job descriptions, verify:
                                          - Returns valid JSON matching JobRequirements schema
                                          - company_name and role_title extracted when present
                                          - technical_skills are real technologies, not invented
                                          - experience_years is a number or null
```

### 9.4 Scraper Tests (Offline)

Maintain HTML fixture files for common job boards:

```
tests/fixtures/scraper/
    greenhouse_job.html
    lever_job.html
    linkedin_job.html
    workday_job.html
    static_career_page.html
```

Test `_extract_job_text()` against each fixture to verify extraction quality without network calls.

---

## 10. Edge Cases & Error Handling

| Scenario | Handling |
|---|---|
| URL returns a 404 | Fail scrape task with "Job posting not found — it may have been removed." |
| URL returns a login wall | Playwright heuristic: if page has <50 words of content and contains "sign in" or "log in", fail with "This page requires login — please paste the job description." |
| CAPTCHA detected | Fail with "CAPTCHA detected — please paste the job description manually." |
| Job description is in a non-English language | Extract requirements as-is. The embedding model handles multilingual input. The requirements extraction prompt works in English but the LLM can understand non-English input. |
| Job URL points to a PDF | Detect via Content-Type header. Download, extract text via `pdfplumber`, treat as `raw_text`. Skip Playwright. |
| Same URL submitted twice by same user | Check `idx_jobs_url` index. If same URL exists and was created <1 hour ago, return the existing job row instead of re-scraping. |
| LLM returns `experience_years: "5+"` (string instead of int) | Pydantic coercion should handle this. If not, parse manually: strip non-numeric chars, cast to int. |
| Vault has 0 embedded nodes when match is requested | Return empty `matched_nodes` list and `low_relevance_warning = true`. |
| Vault has <5 embedded nodes | Return all available nodes (may be 1-4). Do not pad with irrelevant results. |

---

## 11. Data Flow

```
Input:     Job URL or raw text (from user)
                │
                ▼
         ┌──────────────┐
         │   SCRAPE      │  Playwright / httpx
         │   (if URL)    │
         └──────┬───────┘
                │ raw_text
                ▼
         ┌──────────────┐
         │   EXTRACT     │  Claude Sonnet → JobRequirements JSON
         └──────┬───────┘
                │ JobRequirements
                ▼
         ┌──────────────┐
         │   EMBED       │  text-embedding-3-small → 1536-dim vector
         └──────┬───────┘
                │ vector
                ▼
         ┌──────────────┐
         │   MATCH       │  pgvector cosine similarity vs experience_nodes
         └──────┬───────┘
                │
                ▼
Output:    MatchResult {
               job_requirements: JobRequirements,
               matched_nodes: ExperienceNodeResult[0..5],
               low_relevance_warning: bool
           }
           → Consumed by Document Assembly pipeline
```

---

*This document is self-contained for building the Semantic Matcher module. For shared infrastructure, see `architecture.md`. For the Experience Vault that this module queries, see `pipeline-experience-vault.md` (read-only dependency — no coordination needed).*
