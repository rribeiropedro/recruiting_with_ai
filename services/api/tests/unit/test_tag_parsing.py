import pytest


def test_parse_tags_response_accepts_json_array():
    from app.tasks.embed_tasks import parse_tags_response

    assert parse_tags_response('["Python", "machine learning", "python"]') == [
        "python",
        "machine-learning",
    ]


def test_parse_tags_response_accepts_fenced_json():
    from app.tasks.embed_tasks import parse_tags_response

    assert parse_tags_response('```json\n["hpc", "mpi"]\n```') == ["hpc", "mpi"]


def test_parse_tags_response_accepts_tags_object():
    from app.tasks.embed_tasks import parse_tags_response

    assert parse_tags_response('{"tags": ["react", "typescript"]}') == ["react", "typescript"]


@pytest.mark.parametrize("raw", ['{"tag": "python"}', '"python"', "[1, 2]"])
def test_parse_tags_response_rejects_malformed_shapes(raw):
    from app.tasks.embed_tasks import parse_tags_response

    with pytest.raises(ValueError):
        parse_tags_response(raw)
