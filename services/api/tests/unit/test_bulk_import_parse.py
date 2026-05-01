import pytest


def test_parse_bulk_nodes_response_accepts_array():
    from app.tasks.scrape_tasks import parse_bulk_nodes_response

    nodes = parse_bulk_nodes_response(
        """
        [
          {
            "title": "Robotics Hackathon",
            "organization": "Campus Robotics",
            "role": "Team Lead",
            "start_date": "2024-02",
            "end_date": null,
            "description": "Built a path-planning demo for a robotics hackathon.",
            "bullet_points": ["Led a four-person team."],
            "node_type": "hackathon"
          }
        ]
        """
    )

    assert len(nodes) == 1
    assert nodes[0].node_type == "hackathon"
    assert nodes[0].start_date.month == 2


def test_parse_bulk_nodes_response_accepts_nodes_object():
    from app.tasks.scrape_tasks import parse_bulk_nodes_response

    nodes = parse_bulk_nodes_response(
        '{"nodes":[{"title":"Degree","description":"Completed a computer science degree.",'
        '"bullet_points":[],"node_type":"education"}]}'
    )

    assert nodes[0].title == "Degree"


@pytest.mark.parametrize("raw", ["not json", "[]", '{"title":"missing array"}'])
def test_parse_bulk_nodes_response_rejects_bad_payloads(raw):
    from app.tasks.scrape_tasks import BulkImportParseError, parse_bulk_nodes_response

    with pytest.raises(BulkImportParseError):
        parse_bulk_nodes_response(raw)
