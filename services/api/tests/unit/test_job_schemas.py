from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError


def test_submit_request_accepts_https_url_only():
    from app.schemas.jobs import JobSubmitRequest

    payload = JobSubmitRequest(url=" https://example.com/jobs/1 ")

    assert payload.url == "https://example.com/jobs/1"
    assert payload.raw_text is None


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"url": "https://example.com/jobs/1", "raw_text": "Job text"},
        {"url": "http://example.com/jobs/1"},
        {"url": ""},
    ],
)
def test_submit_request_rejects_invalid_input(payload):
    from app.schemas.jobs import JobSubmitRequest

    with pytest.raises(ValidationError):
        JobSubmitRequest(**payload)


def test_job_requirements_defaults_and_year_coercion():
    from app.schemas.shared import JobRequirements

    requirements = JobRequirements(experience_years="5+")

    assert requirements.experience_years == 5
    assert requirements.technical_skills == []
    assert requirements.nice_to_haves == []


def test_job_description_response_contract():
    from app.schemas.jobs import JobDescriptionResponse

    job_id = uuid4()
    created_at = datetime.now(UTC)
    response = JobDescriptionResponse(
        id=job_id,
        url=None,
        company_name=None,
        role_title="Backend Engineer",
        requirements={"role_title": "Backend Engineer", "technical_skills": ["Python"]},
        is_embedded=False,
        status="pending",
        error_message=None,
        created_at=created_at,
        updated_at=created_at,
    )

    assert response.id == job_id
    assert response.requirements.technical_skills == ["Python"]
    assert response.status == "pending"
