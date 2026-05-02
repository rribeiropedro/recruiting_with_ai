from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError


def test_generate_application_request_defaults_to_modern_template():
    from app.schemas.application import GenerateApplicationRequest

    job_id = uuid4()
    request = GenerateApplicationRequest(job_description_id=job_id)

    assert request.job_description_id == job_id
    assert request.template == "modern"


def test_generate_application_request_rejects_unknown_template():
    from app.schemas.application import GenerateApplicationRequest

    with pytest.raises(ValidationError):
        GenerateApplicationRequest(job_description_id=uuid4(), template="creative")


def test_generate_from_url_request_accepts_https_url_and_trims_input():
    from app.schemas.application import GenerateFromUrlRequest

    request = GenerateFromUrlRequest(url=" https://example.com/jobs/1 ")

    assert request.url == "https://example.com/jobs/1"
    assert request.raw_text is None
    assert request.template == "modern"


def test_generate_from_url_request_accepts_raw_text_fallback():
    from app.schemas.application import GenerateFromUrlRequest

    request = GenerateFromUrlRequest(raw_text=" Senior Python role ")

    assert request.raw_text == "Senior Python role"
    assert request.url is None


@pytest.mark.parametrize("payload", [{}, {"url": ""}, {"url": "http://example.com/jobs/1"}])
def test_generate_from_url_request_rejects_invalid_input(payload):
    from app.schemas.application import GenerateFromUrlRequest

    with pytest.raises(ValidationError):
        GenerateFromUrlRequest(**payload)


def test_application_status_response_contract():
    from app.schemas.application import ApplicationStatusResponse

    app_id = uuid4()
    created_at = datetime.now(UTC)
    response = ApplicationStatusResponse(
        id=app_id,
        status="completed",
        error_message=None,
        cache_hit=False,
        company_name="Acme",
        role_title="Backend Engineer",
        matched_node_count=3,
        pdf_url="https://signed.example/resume.pdf",
        created_at=created_at,
        completed_at=created_at,
    )

    assert response.id == app_id
    assert response.status == "completed"
    assert response.matched_node_count == 3


def test_application_detail_response_extends_status_contract():
    from app.schemas.application import ApplicationDetailResponse

    created_at = datetime.now(UTC)
    response = ApplicationDetailResponse(
        id=uuid4(),
        status="rewriting",
        error_message=None,
        cache_hit=True,
        company_name=None,
        role_title="ML Engineer",
        matched_node_count=1,
        pdf_url=None,
        created_at=created_at,
        completed_at=None,
        matched_nodes=[{"node_id": str(uuid4()), "bullet_points": ["Built ranking model"]}],
        similarity_scores=[0.82],
        job_requirements={"technical_skills": ["Python"]},
    )

    assert response.cache_hit is True
    assert response.matched_nodes[0]["bullet_points"] == ["Built ranking model"]
    assert response.job_requirements["technical_skills"] == ["Python"]


def test_generated_application_summary_accepts_public_contract_field():
    from app.schemas.shared import GeneratedApplicationSummary

    summary = GeneratedApplicationSummary(
        application_id=uuid4(),
        job_description_id=uuid4(),
        company_name="Acme",
        role_title="Backend Engineer",
        pdf_storage_path="resumes/user/app.pdf",
        pdf_url="https://signed.example/resume.pdf",
        tailored_content={"nodes": []},
        resume_text_summary="Tailored backend resume summary.",
    )

    assert summary.resume_text_summary == "Tailored backend resume summary."


def test_generated_application_summary_accepts_database_resume_summary_alias():
    from app.schemas.shared import GeneratedApplicationSummary

    summary = GeneratedApplicationSummary(
        application_id=uuid4(),
        job_description_id=uuid4(),
        company_name=None,
        role_title=None,
        pdf_storage_path="resumes/user/app.pdf",
        pdf_url="https://signed.example/resume.pdf",
        tailored_content={"nodes": []},
        resume_summary="Database column summary.",
    )

    assert summary.resume_text_summary == "Database column summary."
    assert "resume_text_summary" in summary.model_dump()
