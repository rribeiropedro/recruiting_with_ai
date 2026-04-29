import asyncio

import asyncpg
from supabase import create_client

from app.config import settings


def _pg_dsn(url: str) -> str:
    """Strip SQLAlchemy driver prefix; asyncpg takes plain postgresql://."""
    return url.replace("postgresql+asyncpg://", "postgresql://")


async def _connect(url: str, pooler: bool = False) -> asyncpg.Connection:
    kwargs: dict = {"ssl": "require"}
    if pooler:
        kwargs["statement_cache_size"] = 0
    return await asyncpg.connect(_pg_dsn(url), **kwargs)


async def _connect_any() -> asyncpg.Connection:
    """Try direct connection first; fall back to pooler if port 5432 is blocked."""
    try:
        return await _connect(settings.DATABASE_URL)
    except OSError:
        return await _connect(settings.DATABASE_URL_POOLED, pooler=True)


async def test_db_direct():
    # Port 5432 is often blocked on home networks/WSL2 — falls back to pooler (6543).
    # On Render, DATABASE_URL (port 5432) connects directly without issue.
    try:
        conn = await _connect(settings.DATABASE_URL)
        port = 5432
    except OSError:
        conn = await _connect(settings.DATABASE_URL_POOLED, pooler=True)
        port = 6543
    result = await conn.fetchval("SELECT 1")
    await conn.close()
    assert result == 1
    print(f"✓ DB connection (port {port})")


async def test_db_pooled():
    conn = await _connect(settings.DATABASE_URL_POOLED, pooler=True)
    result = await conn.fetchval("SELECT 1")
    await conn.close()
    assert result == 1
    print("✓ Pooled DB connection (port 6543)")


async def test_pgvector():
    conn = await _connect_any()
    result = await conn.fetchval(
        "SELECT extname FROM pg_extension WHERE extname = 'vector'"
    )
    await conn.close()
    assert result == "vector", "pgvector not installed — run: CREATE EXTENSION vector;"
    print("✓ pgvector extension present")


async def test_shared_tables():
    conn = await _connect_any()
    tables = await conn.fetch(
        "SELECT tablename FROM pg_tables WHERE schemaname = 'public' AND tablename = ANY($1)",
        ["user_profiles", "llm_usage"],
    )
    found = {row["tablename"] for row in tables}
    await conn.close()
    missing = {"user_profiles", "llm_usage"} - found
    assert not missing, f"Missing tables: {missing} — run 00001_shared_tables.sql"
    print("✓ Shared tables exist (user_profiles, llm_usage)")


def test_supabase_rest():
    client = create_client(settings.SUPABASE_URL, settings.SUPABASE_ANON_KEY)
    client.table("user_profiles").select("user_id").limit(1).execute()
    print("✓ Supabase REST API reachable")


async def main():
    print("\nTesting Supabase connection...\n")
    await test_db_direct()
    await test_db_pooled()
    await test_pgvector()
    await test_shared_tables()
    test_supabase_rest()
    print("\nAll checks passed.")


if __name__ == "__main__":
    asyncio.run(main())
