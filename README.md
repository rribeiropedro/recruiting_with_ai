# Career Engine V2

Autonomous job application engine. See `docs/architecture.md` for the full system design.

## Structure

```
apps/web          Next.js 14 frontend (Vercel)
services/api      FastAPI backend + Celery workers (Railway)
infrastructure    Docker Compose (local), Railway config, Supabase migrations
docs              Architecture + per-pipeline specs
```

## Local Dev

### Prerequisites
- Docker & Docker Compose
- Node 20+, Python 3.12+

### Backend

```bash
cd services/api
cp .env.example .env          # fill in values
docker compose -f ../../infrastructure/docker-compose.yml up
```

API: http://localhost:8000  
Docs: http://localhost:8000/docs

### Frontend

```bash
cd apps/web
cp .env.local.example .env.local   # fill in values
npm install
npm run dev
```

App: http://localhost:3000

## Cloud Setup

See `docs/architecture.md` §9 for Railway + Vercel + Supabase deployment steps.
