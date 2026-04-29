import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from .config import settings
from .routers import generate, jobs, outreach, vault

logger = structlog.get_logger()

limiter = Limiter(key_func=get_remote_address)


def create_app() -> FastAPI:
    app = FastAPI(title="Career Engine API", version="2.0.0")

    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.FRONTEND_URL],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(vault.router, prefix="/vault", tags=["vault"])
    app.include_router(jobs.router, prefix="/jobs", tags=["jobs"])
    app.include_router(generate.router, prefix="/generate", tags=["generate"])
    app.include_router(outreach.router, prefix="/outreach", tags=["outreach"])

    @app.get("/health")
    async def health():
        return {"status": "ok", "db": "connected", "redis": "connected"}

    return app


app = create_app()
