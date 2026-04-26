# Autonomous Career Engine V2 — Master Architecture Overview

> **Document role:** Shared infrastructure, cross-cutting concerns, and inter-module contracts. Each module has its own self-contained spec: `pipeline-experience-vault.md`, `pipeline-semantic-matcher.md`, `pipeline-document-assembly.md`, `pipeline-outreach-crm.md`. Agents working on a specific module should read **this doc first** for context, then their pipeline doc for implementation details. This doc does NOT contain enough detail to build any single module — that's by design.

---

## 1. Platform Overview & Philosophy

### 1.1 Problem Statement

Traditional job applications are passive: a candidate uploads a single static PDF resume to a portal and hopes for a match. The resume cannot adapt to each role's language, the candidate has no direct line to the hiring manager, and there is no feedback loop to iterate on positioning.

### 1.2 Solution — Two Pillars

- **The Experience Vault** — A structured, vector-embedded PostgreSQL database of atomic professional "nodes" (individual projects, roles, research clusters, hackathons, certifications). Each node is independently retrievable via semantic similarity, replacing the static PDF resume entirely. → `pipeline-experience-vault.md`
- **The Outreach Engine** — An end-to-end pipeline that ingests a job description URL, dynamically assembles an ATS-friendly tailored resume from the Vault, discovers and verifies the hiring manager's email, drafts an authentic cold email, and sends it from the user's own inbox. This engine spans three modules: → `pipeline-semantic-matcher.md`, `pipeline-document-assembly.md`, `pipeline-outreach-crm.md`

### 1.3 Design Principles

These principles govern every implementation decision across the codebase. Every pipeline doc must adhere to them:

- **Modularity over monolith.** Each module (Vault, Matcher, Renderer, Outreach) must be independently deployable, testable, and replaceable. Communicate via well-defined internal interfaces, not shared mutable state.
- **Idempotency.** Every background task and API endpoint must be safely retriable. Use unique task IDs and database-level deduplication to prevent duplicate resumes, duplicate emails, or duplicate nodes.
- **Cost awareness.** LLM calls and embedding generations are the primary variable cost. Every pipeline must implement caching (embedding similarity thresholds, cached PDFs) and batch processing to minimize API spend.
- **Auditability.** Every generated resume, every sent email, every LLM prompt/response pair must be logged and retrievable. The user must be able to inspect exactly what was sent on their behalf.
- **Graceful degradation.** If a scraper fails, the user can paste raw text. If email verification fails, the draft is still surfaced for manual sending. No single external dependency failure should block the entire pipeline.

---

## 2. System Architecture

### 2.1 High-Level Component Map

```
┌─────────────────────────────────────────────────────────────────┐
│                        CLIENT LAYER                             │
│                  React / Next.js (Vercel)                       │
│   ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────────┐   │
│   │ Vault UI │  │ Job Input│  │ CRM Dash │  │ Settings/Auth│   │
│   └────┬─────┘  └────┬─────┘  └────┬─────┘  └──────┬───────┘   │
└────────┼──────────────┼────────────┼────────────────┼───────────┘
         │              │            │                │
         ▼              ▼            ▼                ▼
┌─────────────────────────────────────────────────────────────────┐
│                       API GATEWAY                               │
│                   FastAPI (Python 3.12+)                         │
│   ┌──────────────────────────────────────────────────────────┐  │
│   │  Auth Middleware (Supabase JWT) → Rate Limiter → Router  │  │
│   └──────────────────────────────────────────────────────────┘  │
│   Routes:  /vault/*   /jobs/*   /generate/*   /outreach/*       │
└────────┬──────────────┬────────────┬────────────────┬───────────┘
         │              │            │                │
         ▼              ▼            ▼                ▼
┌─────────────────────────────────────────────────────────────────┐
│                     TASK WORKER LAYER                            │
│               Celery Workers + Redis Broker                      │
│   ┌────────────┐ ┌────────────┐ ┌────────────┐ ┌────────────┐  │
│   │ Scraper    │ │ Embedder   │ │ PDF Gen    │ │ Email Send │  │
│   │ Worker     │ │ Worker     │ │ Worker     │ │ Worker     │  │
│   └─────┬──────┘ └─────┬──────┘ └─────┬──────┘ └─────┬──────┘  │
└─────────┼──────────────┼──────────────┼──────────────┼──────────┘
          │              │              │              │
          ▼              ▼              ▼              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      DATA & STORAGE LAYER                       │
│  ┌──────────────────┐  ┌─────────────┐  ┌───────────────────┐  │
│  │ Supabase Postgres │  │  Supabase   │  │    Redis          │  │
│  │ + pgvector        │  │  Storage    │  │  (Broker + Cache) │  │
│  │ (Primary DB)      │  │  (PDFs)     │  │                   │  │
│  └──────────────────┘  └─────────────┘  └───────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

### 2.2 Module Ownership Map

This table defines which pipeline doc owns which files, routes, and tables. If two agents need to touch the same file, they must coordinate.

| Module | Pipeline Doc | Owns Routes | Owns Tables | Owns Services | Owns Tasks |
|---|---|---|---|---|---|
| Experience Vault | `pipeline-experience-vault.md` | `/vault/*` | `experience_nodes` | `embedder.py`, `matcher.py` (embedding half) | `embed_tasks.py`, `scrape_tasks.py` (bulk import) |
| Semantic Matcher | `pipeline-semantic-matcher.md` | `/jobs/*` | `job_descriptions` | `scraper.py`, `matcher.py` (query half) | `scrape_tasks.py` (job scraping) |
| Document Assembly | `pipeline-document-assembly.md` | `/generate/*` | `generated_applications` | `rewriter.py`, `renderer.py` | `generate_tasks.py` |
| Outreach CRM | `pipeline-outreach-crm.md` | `/outreach/*`, `/user/oauth/*` | `outreach_campaigns` | `email_drafter.py`, `email_sender.py`, `contact_finder.py` | `outreach_tasks.py` |

**Shared ownership (this doc):** `user_profiles`, `llm_usage`, `auth middleware`, `celery_app.py`, `config.py`, `dependencies.py`, `main.py`.

### 2.3 Tech Stack — Definitive Choices

| Layer | Technology | Version | Rationale |
|---|---|---|---|
| Frontend Framework | Next.js (App Router) | 14.x+ | Server components for SEO, API routes as BFF proxy, built-in image optimization. Deploy on Vercel for edge routing. |
| UI Library | React | 18.x+ | Component model, hooks, concurrent features. |
| UI Styling | Tailwind CSS + shadcn/ui | Latest | Utility-first, consistent design tokens, accessible component primitives. |
| State Management | Zustand | Latest | Lightweight, no boilerplate, works with SSR. Use for client-side CRM state and Vault form state. |
| Real-time Client | Supabase Realtime (JS SDK) | Latest | WebSocket subscriptions for CRM card status changes. |
| Backend API | FastAPI | 0.110+ | Async-native, automatic OpenAPI docs, Pydantic v2 validation, dependency injection. |
| Task Queue | Celery | 5.3+ | Mature distributed task queue. Use `task_acks_late=True` and `task_reject_on_worker_lost=True` for reliability. |
| Message Broker | Redis | 7.x | Celery broker + result backend + short-lived cache layer. |
| Primary Database | Supabase (PostgreSQL 15+) | Latest | Managed Postgres with pgvector extension, Row Level Security, built-in auth. |
| Vector Extension | pgvector | 0.7+ | Cosine distance operator (`<=>`), HNSW indexing. |
| Object Storage | Supabase Storage | Latest | S3-compatible. Store generated PDFs, uploaded resumes, email attachments. |
| PDF Rendering | WeasyPrint | 61+ | HTML/CSS to PDF. ATS-friendly flat PDFs without JavaScript dependencies. |
| Web Scraping | Playwright | Latest | Headless Chromium for JS-rendered job pages. Falls back to `httpx` + BeautifulSoup for static pages. |
| LLM Provider | Anthropic (Claude) | claude-sonnet-4-20250514 | Primary model for rewriting, email drafting, requirements extraction. Use `claude-haiku-4-5-20251001` for metadata tagging (cost optimization). |
| Embedding Model | OpenAI `text-embedding-3-small` | Latest | 1536-dimension embeddings. Good balance of cost and quality. |
| Email Verification | Hunter.io / Apollo.io | Latest | Discover and verify hiring manager emails. |
| OAuth Email Sending | Google Gmail API / Microsoft Graph API | Latest | Send from user's own inbox via OAuth 2.0 consent. |
| Containerization | Docker | Latest | Single Dockerfile for API + workers. Multi-stage build for minimal image size. |
| Hosting (Backend) | Render | N/A | Private networking for API ↔ Worker ↔ Redis. Managed Redis add-on. |
| Hosting (Frontend) | Vercel | N/A | Edge routing, preview deployments, environment variable management. |

### 2.4 Repository Structure

```
career-engine-v2/
├── apps/
│   └── web/                          # Next.js frontend
│       ├── app/                      # App Router pages
│       │   ├── (auth)/               # Auth-gated layout group
│       │   │   ├── vault/            # Experience Vault CRUD UI
│       │   │   ├── generate/         # Job URL input + generation status
│       │   │   ├── outreach/         # CRM Kanban dashboard
│       │   │   └── settings/         # Profile, OAuth connections, templates
│       │   ├── api/                  # Next.js API routes (BFF proxy)
│       │   └── layout.tsx
│       ├── components/
│       │   ├── ui/                   # shadcn/ui primitives
│       │   ├── vault/                # Vault-specific components
│       │   ├── crm/                  # Kanban board, card components
│       │   └── shared/               # Layout, nav, modals
│       ├── lib/
│       │   ├── supabase/             # Client + server Supabase helpers
│       │   ├── stores/               # Zustand stores
│       │   └── utils/
│       ├── public/
│       ├── next.config.js
│       ├── tailwind.config.ts
│       └── package.json
├── services/
│   └── api/                          # FastAPI backend
│       ├── app/
│       │   ├── main.py               # FastAPI app factory, middleware registration
│       │   ├── config.py             # Pydantic Settings (env vars)
│       │   ├── dependencies.py       # Dependency injection (DB sessions, auth)
│       │   ├── models/               # SQLAlchemy / Pydantic models
│       │   ├── schemas/              # Pydantic request/response schemas
│       │   ├── routers/              # FastAPI route handlers
│       │   ├── services/             # Business logic layer
│       │   ├── tasks/                # Celery task definitions
│       │   ├── prompts/              # LLM prompt templates (version-controlled)
│       │   ├── templates/            # HTML/CSS resume templates
│       │   └── utils/
│       ├── migrations/               # Alembic migrations
│       ├── tests/
│       ├── Dockerfile
│       ├── requirements.txt
│       └── pyproject.toml
├── infrastructure/
│   ├── docker-compose.yml            # Local dev: Postgres + Redis + API + Worker
│   ├── render.yaml                   # Render Blueprint (IaC)
│   └── supabase/
│       ├── migrations/               # Supabase SQL migrations
│       └── seed.sql
├── docs/
│   ├── architecture.md               # THIS FILE
│   ├── pipeline-experience-vault.md
│   ├── pipeline-semantic-matcher.md
│   ├── pipeline-document-assembly.md
│   └── pipeline-outreach-crm.md
└── README.md
```

---

## 3. Shared Data Models

### 3.1 Global Database Conventions

- All tables live in the `public` schema with Row Level Security (RLS) enabled.
- Every table includes `user_id UUID REFERENCES auth.users(id)` and an RLS policy restricting access to `auth.uid() = user_id`.
- All embeddings use **1536 dimensions** (matching `text-embedding-3-small`). If the embedding model changes, a migration must re-embed all existing data.
- All timestamps are `TIMESTAMPTZ` in UTC.
- Soft deletes via `is_archived BOOLEAN` where applicable. Never hard-delete user data.

### 3.2 RLS Policy Template

Apply this pattern to every table:

```sql
ALTER TABLE <table_name> ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can only access their own rows"
    ON <table_name>
    FOR ALL
    USING (auth.uid() = user_id)
    WITH CHECK (auth.uid() = user_id);
```

### 3.3 `user_profiles` (Shared — Not Owned by Any Pipeline)

```sql
CREATE TABLE user_profiles (
    user_id             UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    full_name           TEXT NOT NULL,
    email               TEXT NOT NULL,
    phone               TEXT,
    location            TEXT,
    linkedin_url        TEXT,
    portfolio_url       TEXT,
    github_url          TEXT,
    headline            TEXT,                              -- "Software Engineer | HPC Researcher"
    gmail_oauth_token   JSONB,                             -- Encrypted OAuth2 credentials
    outlook_oauth_token JSONB,
    preferred_template  TEXT DEFAULT 'modern',
    target_industries   TEXT[] DEFAULT '{}',
    target_roles        TEXT[] DEFAULT '{}',
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    updated_at          TIMESTAMPTZ DEFAULT NOW()
);
```

### 3.4 `llm_usage` (Shared Audit Table)

```sql
CREATE TABLE llm_usage (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES auth.users(id),
    task_type       TEXT NOT NULL,       -- 'tag', 'embed', 'extract', 'rewrite', 'draft_email'
    model           TEXT NOT NULL,
    input_tokens    INT NOT NULL,
    output_tokens   INT NOT NULL,
    cost_usd        DECIMAL(10, 6),
    prompt_version  TEXT,                -- e.g. "rewrite_v3"
    created_at      TIMESTAMPTZ DEFAULT NOW()
);
```

### 3.5 Inter-Module Data Contracts

These are the data shapes that cross module boundaries. Each producing module must output this exact shape; each consuming module can depend on it.

**Vault → Matcher / Document Assembly: `ExperienceNodeResult`**

```python
class ExperienceNodeResult(BaseModel):
    id: UUID
    title: str
    organization: str | None
    role: str | None
    start_date: date | None
    end_date: date | None
    description: str
    bullet_points: list[str]
    node_type: str
    tags: list[str]
    similarity_score: float  # Added by Matcher, not stored on the node itself
```

**Matcher → Document Assembly: `JobRequirements`**

```python
class JobRequirements(BaseModel):
    company_name: str | None
    role_title: str | None
    technical_skills: list[str]
    soft_skills: list[str]
    responsibilities: list[str]
    experience_years: int | None
    education: str | None
    nice_to_haves: list[str]
    industry: str | None
```

**Document Assembly → Outreach: `GeneratedApplicationSummary`**

```python
class GeneratedApplicationSummary(BaseModel):
    application_id: UUID
    job_description_id: UUID
    company_name: str | None
    role_title: str | None
    pdf_storage_path: str
    pdf_url: str
    tailored_content: dict  # The rewritten nodes as JSON
    resume_text_summary: str  # Plain text summary for email drafter context
```

---

## 4. Authentication & Authorization

### 4.1 Auth Provider

Use **Supabase Auth** as the sole identity provider. Supports email/password, magic link, and Google OAuth.

### 4.2 JWT Flow

1. Frontend uses the Supabase JS SDK to authenticate. Receives a JWT.
2. Frontend includes the JWT in the `Authorization: Bearer <token>` header for all FastAPI requests.
3. FastAPI middleware decodes and validates the JWT using `SUPABASE_JWT_SECRET`. Extracts `user_id` from the `sub` claim.
4. The `user_id` is injected into every route handler via FastAPI's dependency injection.

### 4.3 Service Role for Workers

Celery workers connect using the Supabase `service_role` key, which bypasses RLS. This key must be stored securely and never exposed to the frontend.

### 4.4 Auth Middleware Implementation

```python
# dependencies.py
from fastapi import Depends, HTTPException, Header
import jwt

async def get_current_user(authorization: str = Header(...)) -> UUID:
    token = authorization.replace("Bearer ", "")
    try:
        payload = jwt.decode(token, settings.SUPABASE_JWT_SECRET, algorithms=["HS256"],
                             audience="authenticated")
        return UUID(payload["sub"])
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")
```

---

## 5. LLM Integration Layer (Shared)

### 5.1 Abstraction

All LLM calls go through a single `services/llm_client.py` module. This module is shared across all pipelines.

```python
# services/llm_client.py — Interface contract
class LLMClient:
    async def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        model: str = "claude-sonnet-4-20250514",  # or "claude-haiku-4-5-20251001"
        max_tokens: int = 4096,
        response_format: Literal["text", "json"] = "text",
        user_id: UUID | None = None,        # For cost tracking
        task_type: str | None = None,       # For cost tracking
        prompt_version: str | None = None,  # For audit trail
    ) -> str: ...

    async def embed(
        self,
        text: str,
        user_id: UUID | None = None,
    ) -> list[float]: ...  # Returns 1536-dim vector
```

### 5.2 Retry Policy

- Rate limits (429): Retry with exponential backoff — 2s, 4s, 8s, 16s. Max 4 retries.
- Server errors (500, 503): Retry with exponential backoff — 5s, 15s, 45s. Max 3 retries.
- Timeouts: 60s per call. Retry once.
- All retries are logged with the attempt number.

### 5.3 Cost Tracking

Every `complete()` and `embed()` call writes a row to `llm_usage` with token counts and computed cost. The cost computation uses a hardcoded pricing table that must be updated when model pricing changes.

### 5.4 Prompt Version Control

All prompts live in `app/prompts/` as Python modules with a `VERSION` constant. Each pipeline doc specifies its own prompts. The `llm_client` logs the `prompt_version` on every call.

---

## 6. Background Task System (Shared)

### 6.1 Celery Configuration

```python
# tasks/celery_app.py
from celery import Celery

app = Celery("career_engine")

app.conf.update(
    broker_url=settings.REDIS_URL,
    result_backend=settings.REDIS_URL,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_track_started=True,
    task_time_limit=300,                    # Hard kill after 5 minutes
    task_soft_time_limit=240,               # SoftTimeLimitExceeded at 4 minutes
    worker_max_tasks_per_child=50,          # Restart worker after 50 tasks (Playwright memory)
    broker_connection_retry_on_startup=True,
)
```

### 6.2 Queue Architecture

| Queue | Workers | Concurrency | Purpose |
|---|---|---|---|
| `default` | `career-engine-worker-default` | 4 | Tagging, embedding, email drafting |
| `heavy` | `career-engine-worker-heavy` | 2 | Scraping (Playwright), full generation pipeline |
| `email` | (shares `default` worker) | 1 | Email sending — serial to prevent rate limiting |

### 6.3 Task Status Pattern

Every long-running task follows this pattern:

1. API creates a DB row with `status = 'pending'` and a `celery_task_id`.
2. Worker updates `status` at each stage transition.
3. Client polls `GET /resource/{id}` or subscribes via Supabase Realtime.
4. On failure, worker sets `status = 'failed'` and `error_message` in a `finally` block.

---

## 7. Error Handling, Logging & Observability (Shared)

### 7.1 Error Handling

- **API layer:** FastAPI exception handlers catch all unhandled exceptions. Never leak stack traces in production.
- **Task layer:** Every Celery task wraps its body in try/except, updates DB `status` to `failed`, records `error_message`, then re-raises.
- **External services:** Circuit breaker pattern — 5 consecutive failures in 60s opens the circuit for 30s. Use `pybreaker`.

### 7.2 Logging

- Use `structlog` for structured JSON logging.
- Every log entry includes: `user_id`, `request_id`, `task_id`, `timestamp`.
- Levels: `DEBUG` (dev), `INFO` (prod), `WARNING` (degraded), `ERROR` (failures).

### 7.3 Health Check

`GET /health` returns `{ "status": "ok", "db": "connected", "redis": "connected" }`.

---

## 8. Security (Shared)

### 8.1 Data Protection

- Supabase encrypts all data at rest (AES-256).
- OAuth tokens in `user_profiles` encrypted at application level using `cryptography.fernet` with `ENCRYPTION_KEY` env var.
- All connections use TLS. Redis uses `rediss://`.

### 8.2 Input Validation

- All inputs validated via Pydantic schemas with strict type coercion.
- Job URLs: `https://` only.
- Uploaded PDFs: MIME type check, max 10MB.
- Playwright: sandboxed container, never executes user-supplied JS.

### 8.3 Rate Limiting

Apply via `slowapi`:

| Endpoint Group | Limit |
|---|---|
| Vault CRUD (`/vault/*`) | 60 req/min/user |
| Generation (`/generate/*`) | 10 req/min/user |
| Outreach send (`/outreach/*/send`) | 5 req/min/user |

### 8.4 CORS

Allow origins: Vercel frontend domain(s) only. Allow credentials: `true`.

---

## 9. Deployment & Infrastructure (Shared)

### 9.1 Docker Strategy

Single Dockerfile, multi-target (API + Worker). Shared base installs WeasyPrint C-library dependencies (Pango, Cairo, GDK-Pixbuf). Worker target additionally installs Playwright + Chromium.

### 9.2 Database Connection Routing

| Client | Target | Port | Reason |
|---|---|---|---|
| FastAPI | Supabase Direct Connection | 5432 | Long-lived pool via `asyncpg` |
| Celery Workers | Supabase Transaction Pooler | 6543 | Prevents connection exhaustion |
| Next.js SSR | Supabase JS SDK (REST) | 443 | No direct DB connection |

### 9.3 Environment Variables

| Variable | Used By |
|---|---|
| `SUPABASE_URL` | All |
| `SUPABASE_ANON_KEY` | Frontend |
| `SUPABASE_SERVICE_ROLE_KEY` | Workers only |
| `SUPABASE_JWT_SECRET` | API |
| `DATABASE_URL` | API |
| `DATABASE_URL_POOLED` | Workers |
| `REDIS_URL` | API + Workers |
| `ANTHROPIC_API_KEY` | API + Workers |
| `OPENAI_API_KEY` | API + Workers (embeddings) |
| `HUNTER_API_KEY` | Workers (Outreach) |
| `APOLLO_API_KEY` | Workers (Outreach) |
| `GOOGLE_OAUTH_CLIENT_ID` | API (Outreach) |
| `GOOGLE_OAUTH_CLIENT_SECRET` | API (Outreach) |
| `ENCRYPTION_KEY` | API + Workers |
| `CACHE_SIMILARITY_THRESHOLD` | Workers (default 0.88) |

### 9.4 Render Blueprint

```yaml
services:
  - type: web
    name: career-engine-api
    runtime: docker
    dockerfilePath: services/api/Dockerfile
    dockerContext: services/api
    dockerTarget: api
    healthCheckPath: /health

  - type: worker
    name: career-engine-worker-default
    runtime: docker
    dockerfilePath: services/api/Dockerfile
    dockerContext: services/api
    dockerTarget: worker
    dockerCommand: celery -A app.tasks.celery_app worker -Q default --concurrency=4

  - type: worker
    name: career-engine-worker-heavy
    runtime: docker
    dockerfilePath: services/api/Dockerfile
    dockerContext: services/api
    dockerTarget: worker
    dockerCommand: celery -A app.tasks.celery_app worker -Q heavy --concurrency=2

  - type: redis
    name: career-engine-redis
    plan: starter
    maxmemoryPolicy: allkeys-lru
```

### 9.5 CI/CD

- **On PR:** `pytest` (unit + integration), `ruff`, `mypy`, `npm run lint` + `npm run build`.
- **On merge to `main`:** Auto-deploy API + workers to Render. Auto-deploy frontend to Vercel.

---

## 10. Performance Budgets

| Operation | Target | Owner Pipeline |
|---|---|---|
| Vault node creation (before embedding) | < 200ms | Experience Vault |
| Vault node listing | < 300ms | Experience Vault |
| Full application generation (end-to-end) | < 60s | Document Assembly (orchestrates Matcher) |
| Email draft generation | < 15s | Outreach CRM |
| CRM dashboard load | < 500ms | Outreach CRM |

---

## 11. End-to-End Pipeline Flow

This shows how the four modules connect. Each box is fully specified in its own pipeline doc.

```
USER PROVIDES JOB URL
        │
        ▼
┌─────────────────────┐
│  SEMANTIC MATCHER    │  pipeline-semantic-matcher.md
│  1. Scrape URL       │
│  2. Extract reqs     │
│  3. Embed reqs       │
│  Output: JobReqs +   │
│  matched nodes       │
└────────┬────────────┘
         │ ExperienceNodeResult[] + JobRequirements
         ▼
┌─────────────────────┐
│  DOCUMENT ASSEMBLY   │  pipeline-document-assembly.md
│  4. Cache check      │
│  5. Rewrite bullets  │
│  6. Render PDF       │
│  7. Embed resume     │
│  Output: PDF + URL   │
└────────┬────────────┘
         │ GeneratedApplicationSummary
         ▼
┌─────────────────────┐
│  OUTREACH CRM        │  pipeline-outreach-crm.md
│  8. Find contact     │
│  9. Draft email      │
│  10. User reviews    │
│  11. Send from inbox │
│  12. Track replies   │
└─────────────────────┘

EXPERIENCE VAULT (pipeline-experience-vault.md) feeds into
the Matcher at step 3 — it provides the vector-indexed nodes
that the similarity search queries against.
```

---

## 12. Future Extension Points

Out of scope for V2 MVP but the architecture must not preclude:

- Multi-language support (parameterized prompts + templates, multilingual embedding model)
- Analytics dashboard (A/B test resume versions and email templates)
- LinkedIn auto-import (OAuth, node creation from profile data)
- Follow-up automation (3/7/14-day email sequences)
- Team/agency mode (multi-tenant with admin role)
- Job board integrations (Indeed, LinkedIn, Greenhouse, Lever APIs)

---

## Glossary

| Term | Definition |
|---|---|
| **Node** | An atomic unit of professional experience in the Experience Vault |
| **Vault** | The user's complete collection of experience nodes |
| **Embedding** | A 1536-dimensional vector representation of text for semantic similarity search |
| **Cosine similarity** | Similarity measure between two vectors, -1 (opposite) to 1 (identical) |
| **ATS** | Applicant Tracking System — software used by employers to parse and rank resumes |
| **RLS** | Row Level Security — PostgreSQL feature restricting row access by user |
| **RAG** | Retrieval-Augmented Generation — retrieve data then inject into LLM prompt |
| **BFF** | Backend for Frontend — thin API proxy in Next.js layer |
| **Cache hit** | When a sufficiently similar resume exists and can be reused |

---

*This document is the shared infrastructure reference. For module-specific implementation details, see the corresponding pipeline doc. If any pipeline doc contradicts this document on shared concerns (auth, DB conventions, logging, deployment), this document wins.*
