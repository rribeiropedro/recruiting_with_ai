from dataclasses import dataclass


def test_build_embedding_text_with_full_node_dict():
    from app.services.embedder import build_embedding_text

    text = build_embedding_text(
        {
            "title": "Distributed Cache Layer",
            "organization": "Virginia Tech",
            "role": "Research Assistant",
            "description": "Designed a cache for HPC workloads.",
            "bullet_points": ["Reduced tail latency by 35%.", "Used Python and MPI."],
        }
    )

    assert text == (
        "Distributed Cache Layer | at Virginia Tech | as Research Assistant | "
        "Designed a cache for HPC workloads. | Reduced tail latency by 35%. | Used Python and MPI."
    )


def test_build_embedding_text_omits_empty_optional_fields():
    from app.services.embedder import build_embedding_text

    text = build_embedding_text(
        {
            "title": "Portfolio Site",
            "organization": "",
            "role": None,
            "description": "Built a portfolio for project writeups.",
            "bullet_points": [],
        }
    )

    assert text == "Portfolio Site | Built a portfolio for project writeups."


def test_build_embedding_text_accepts_object_nodes():
    from app.services.embedder import build_embedding_text

    @dataclass
    class Node:
        title: str
        organization: str | None
        role: str | None
        description: str
        bullet_points: list[str]

    text = build_embedding_text(
        Node(
            title="ML Pipeline",
            organization=None,
            role="Engineer",
            description="Trained a ranking model.",
            bullet_points=["Improved precision by 12%."],
        )
    )

    assert text == (
        "ML Pipeline | as Engineer | Trained a ranking model. | Improved precision by 12%."
    )
