from uuid import uuid4

import pytest


def test_parse_job_requirements_response_accepts_fenced_json():
    from app.services.matcher import parse_job_requirements_response

    requirements = parse_job_requirements_response(
        """
        ```json
        {
          "company_name": "Acme",
          "role_title": "Platform Engineer",
          "technical_skills": ["Python", "Kubernetes", "Python"],
          "soft_skills": ["Communication"],
          "responsibilities": ["Build internal platforms"],
          "experience_years": "4+ years",
          "education": null,
          "nice_to_haves": ["Terraform"],
          "industry": "SaaS"
        }
        ```
        """
    )

    assert requirements.company_name == "Acme"
    assert requirements.experience_years == 4
    assert requirements.technical_skills == ["Python", "Kubernetes"]


@pytest.mark.parametrize("raw", ["not json", "[]", '"text"'])
def test_parse_job_requirements_response_rejects_bad_payloads(raw):
    from app.services.matcher import JobRequirementExtractionError, parse_job_requirements_response

    with pytest.raises(JobRequirementExtractionError):
        parse_job_requirements_response(raw)


def test_build_job_embedding_text_uses_bounded_relevant_fields():
    from app.schemas.shared import JobRequirements
    from app.services.matcher import build_job_embedding_text

    requirements = JobRequirements(
        role_title="ML Engineer",
        technical_skills=["Python", "PyTorch"],
        responsibilities=[f"Responsibility {idx}" for idx in range(7)],
        education="BS in Computer Science",
        nice_to_haves=["Kubernetes", "Spark", "Airflow", "Terraform"],
    )

    text = build_job_embedding_text(requirements)

    assert text.startswith("ML Engineer | Python | PyTorch")
    assert "Responsibility 4" in text
    assert "Responsibility 5" not in text
    assert "Airflow" in text
    assert "Terraform" not in text


def test_low_relevance_warning_contract():
    from app.schemas.shared import ExperienceNodeResult
    from app.services.matcher import has_low_relevance

    result = ExperienceNodeResult(
        id=uuid4(),
        title="Cache",
        organization=None,
        role=None,
        start_date=None,
        end_date=None,
        description="Built a cache.",
        bullet_points=[],
        node_type="project",
        tags=[],
        similarity_score=0.29,
    )

    assert has_low_relevance([]) is True
    assert has_low_relevance([result]) is True

    result.similarity_score = 0.3
    assert has_low_relevance([result]) is False
