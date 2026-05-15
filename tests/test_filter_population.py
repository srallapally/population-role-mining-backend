# backend/tests/test_filter_population.py
import pytest

from pipeline.filter_population import filter_population


def test_single_value_filter():
    ids, summary = filter_population({"JobCode": "JC10"}, 10000)
    assert set(ids) == {"u001", "u002", "u003", "u007", "u008"}
    assert summary["count"] == 5


def test_array_value_filter():
    ids, summary = filter_population({"JobCode": ["JC10", "JC20"]}, 10000)
    assert len(ids) == 10


def test_multi_key_filter():
    ids, summary = filter_population({"JobCode": "JC10", "WorkLocation": "NYC"}, 10000)
    assert set(ids) == {"u001", "u002", "u003", "u007", "u008"}


def test_population_ids_sorted():
    ids, _ = filter_population({"JobCode": "JC10"}, 10000)
    assert ids == sorted(ids)


def test_zero_matches_raises():
    with pytest.raises(ValueError, match="0 users"):
        filter_population({"JobCode": "NONEXISTENT"}, 10000)


def test_cap_exceeded_raises():
    with pytest.raises(ValueError, match="exceeding cap"):
        filter_population({"JobCode": ["JC10", "JC20"]}, 3)


def test_exactly_at_cap_succeeds():
    ids, _ = filter_population({"JobCode": "JC10"}, 5)
    assert len(ids) == 5


def test_filter_description_format():
    _, summary = filter_population({"JobCode": "JC10"}, 10000)
    assert "JobCode" in summary["filterDescription"]
    assert "JC10" in summary["filterDescription"]