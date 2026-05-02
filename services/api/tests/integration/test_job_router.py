from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException

TEST_USER_ID = uuid4()


def _job_response(**overrides):
    from app.schemas.jobs import JobDescriptionResponse

    now = datetime.now(UTC)
    base = {
        "id": uuid4(),
        "url": "https://example.com/jobs/1",
        "company_name": "Acme",
        "role_title": "Platform Engineer",
        "requirements": {"role_title": "Platform Engineer", "technical_skills": ["Python"]},
        "is_embedded": False,
        "status": "pending",
        "error_message": None,
        "created_at": now,
        "updated_at": now,
    }
    base.update(overrides)
    return JobDescriptionResponse(**base)


@pytest.mark.asyncio
async def test_submit_job_returns_created_response(monkeypatch):
    from app.routers import jobs
    from app.schemas.jobs import JobSubmitRequest
    from app.services import job_service

    async def fake_submit_job(user_id: UUID, payload):
        assert user_id == TEST_USER_ID
        assert payload.url == "https://example.com/jobs/1"
        return _job_response()

    monkeypatch.setattr(job_service, "submit_job", fake_submit_job)

    response = await jobs.submit_job(
        JobSubmitRequest(url="https://example.com/jobs/1"),
        user_id=TEST_USER_ID,
    )

    assert response.status == "pending"
    assert response.requirements.technical_skills == ["Python"]


@pytest.mark.asyncio
async def test_get_job_not_found_returns_404(monkeypatch):
    from app.routers import jobs
    from app.services import job_service

    async def fake_get_job(_user_id: UUID, _job_id: UUID):
        return None

    monkeypatch.setattr(job_service, "get_job", fake_get_job)

    with pytest.raises(HTTPException) as exc_info:
        await jobs.get_job(uuid4(), user_id=TEST_USER_ID)

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "Job not found"


@pytest.mark.asyncio
async def test_match_job_not_ready_returns_409(monkeypatch):
    from app.routers import jobs
    from app.services import job_service

    async def fake_match_job(_user_id: UUID, _job_id: UUID):
        raise job_service.JobNotReady

    monkeypatch.setattr(job_service, "match_job", fake_match_job)

    with pytest.raises(HTTPException) as exc_info:
        await jobs.match_job(uuid4(), user_id=TEST_USER_ID)

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail == "Job description not yet processed"


@pytest.mark.asyncio
async def test_match_job_returns_result(monkeypatch):
    from app.routers import jobs
    from app.schemas.jobs import MatchResult
    from app.schemas.shared import JobRequirements
    from app.services import job_service

    job_id = uuid4()

    async def fake_match_job(user_id: UUID, requested_job_id: UUID):
        assert user_id == TEST_USER_ID
        assert requested_job_id == job_id
        return MatchResult(
            job_description_id=job_id,
            job_requirements=JobRequirements(role_title="Platform Engineer"),
            matched_nodes=[],
            low_relevance_warning=True,
        )

    monkeypatch.setattr(job_service, "match_job", fake_match_job)

    response = await jobs.match_job(job_id, user_id=TEST_USER_ID)

    assert response.job_description_id == job_id
    assert response.low_relevance_warning is True
