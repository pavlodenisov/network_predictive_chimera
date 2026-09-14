"""WebSearchSource (intelligence/ingestion/adapters/web_search.py) — spec addendum.

Pure unit tests: no network, no DB. `_tavily_search` is patched at the module level
so every test exercises the adapter's own query-building, name-parsing, and
degraded-health logic against canned search results.
"""

from __future__ import annotations

import uuid
from datetime import date
from types import SimpleNamespace
from unittest.mock import patch

from intelligence.ingestion.adapters.base import PersonRef
from intelligence.ingestion.adapters.web_search import (
    WebSearchSource,
    _linkedin_query,
    _parse_linkedin_name,
)
from intelligence.models.enums import ContentType, SourceHealthStatus

AS_OF = date(2026, 9, 13)


def rule(**kw):
    defaults = {"active": True, "titles": [], "geographies": []}
    defaults.update(kw)
    return SimpleNamespace(**defaults)


# --------------------------------------------------------------------- name parsing
def test_parse_linkedin_name_with_headline():
    assert (
        _parse_linkedin_name(
            "Jane Doe - Founder at Acme | LinkedIn", "https://www.linkedin.com/in/janedoe"
        )
        == "Jane Doe"
    )


def test_parse_linkedin_name_without_headline():
    assert (
        _parse_linkedin_name("Jane Doe | LinkedIn", "https://www.linkedin.com/in/janedoe")
        == "Jane Doe"
    )


def test_parse_linkedin_name_rejects_non_profile_url():
    # a company page or search-results page — not a person
    assert _parse_linkedin_name("Acme Corp | LinkedIn", "https://www.linkedin.com/company/acme") is None


def test_parse_linkedin_name_rejects_non_linkedin_title():
    assert _parse_linkedin_name("Acme raises $2M seed round", "https://techcrunch.com/x") is None


def test_parse_linkedin_name_rejects_single_word():
    # e.g. a company/brand page mis-scoped to /in/ — not a plausible person name
    assert _parse_linkedin_name("TechCrunch | LinkedIn", "https://www.linkedin.com/in/techcrunch") is None


def test_parse_linkedin_name_rejects_non_name_tokens():
    # digits / lowercase-leading tokens never pass as a name — never a guess
    assert _parse_linkedin_name("jane99 doe | LinkedIn", "https://www.linkedin.com/in/jane99doe") is None


def test_parse_linkedin_name_rejects_too_many_words():
    long_title = "Jane Middle One Two Three Four | LinkedIn"
    assert _parse_linkedin_name(long_title, "https://www.linkedin.com/in/x") is None


# --------------------------------------------------------------------- query building
def test_linkedin_query_requires_titles():
    assert _linkedin_query(rule(titles=[])) is None


def test_linkedin_query_includes_titles_and_geographies():
    q = _linkedin_query(rule(titles=["Founder", "General Partner"], geographies=["Bangalore"]))
    assert q is not None
    assert "site:linkedin.com/in" in q
    assert "Founder" in q
    assert "Bangalore" in q


# --------------------------------------------------------------------- disabled behavior
def test_disabled_without_api_key_returns_empty_and_reports_disabled():
    source = WebSearchSource(api_key="")
    assert source.update_known_entities(people=[], as_of=AS_OF) == []
    assert source.discover(rules=[rule(titles=["Founder"])], as_of=AS_OF) == []
    health = source.health_check()
    assert health.status == SourceHealthStatus.DISABLED


# --------------------------------------------------------------------- update_known_entities
def test_update_known_entities_queries_each_person_and_attributes_results():
    canned = [
        {
            "title": "Jane Doe raises seed round for new startup",
            "content": "Jane Doe has raised a $2M seed round.",
            "url": "https://techcrunch.com/jane-doe-raise",
            "published_date": "2026-09-10",
        }
    ]
    people = [
        PersonRef(person_id=uuid.uuid4(), canonical_name="Jane Doe"),
        PersonRef(person_id=uuid.uuid4(), canonical_name="Amir Khan"),
    ]
    with patch(
        "intelligence.ingestion.adapters.web_search._tavily_search", return_value=canned
    ) as mock_search:
        source = WebSearchSource(api_key="test-key")
        drafts = source.update_known_entities(people=people, as_of=AS_OF)

    assert mock_search.call_count == 2  # one query per known person
    assert len(drafts) == 2  # each query returned the same canned result
    names = {d.subject_hint for d in drafts}
    assert names == {"Jane Doe", "Amir Khan"}
    d = drafts[0]
    assert d.content_type == ContentType.NEWS_ARTICLE
    assert d.source_url == "https://techcrunch.com/jane-doe-raise"
    assert d.occurred_at is not None and d.occurred_at.year == 2026


# --------------------------------------------------------------------- discover
def test_discover_only_queries_rules_with_titles():
    with patch("intelligence.ingestion.adapters.web_search._tavily_search", return_value=[]) as mock_search:
        source = WebSearchSource(api_key="test-key")
        source.discover(rules=[rule(titles=[]), rule(titles=[]), rule(titles=[])], as_of=AS_OF)
    mock_search.assert_not_called()


def test_discover_skips_inactive_rules():
    with patch("intelligence.ingestion.adapters.web_search._tavily_search", return_value=[]) as mock_search:
        source = WebSearchSource(api_key="test-key")
        source.discover(rules=[rule(titles=["Founder"], active=False)], as_of=AS_OF)
    mock_search.assert_not_called()


def test_discover_only_creates_candidates_for_parseable_linkedin_names():
    canned = [
        {
            "title": "Priya Sharma - Founder at Nimbus | LinkedIn",
            "content": "",
            "url": "https://www.linkedin.com/in/priyasharma",
        },
        {
            # a search result that happened to match but isn't a clean profile page —
            # must never turn into a guessed candidate
            "title": "10 Bangalore Founders To Watch",
            "content": "",
            "url": "https://example.com/list",
        },
    ]
    with patch("intelligence.ingestion.adapters.web_search._tavily_search", return_value=canned):
        source = WebSearchSource(api_key="test-key")
        drafts = source.discover(rules=[rule(titles=["Founder"], geographies=["Bangalore"])], as_of=AS_OF)

    assert len(drafts) == 1
    assert drafts[0].subject_hint == "Priya Sharma"
    assert drafts[0].source_url == "https://www.linkedin.com/in/priyasharma"


# --------------------------------------------------------------------- degraded health
def test_search_failure_is_recorded_not_raised():
    with patch(
        "intelligence.ingestion.adapters.web_search._tavily_search", side_effect=RuntimeError("boom")
    ):
        source = WebSearchSource(api_key="test-key")
        drafts = source.update_known_entities(
            people=[PersonRef(person_id=uuid.uuid4(), canonical_name="Jane Doe")],
            as_of=AS_OF,
        )
    assert drafts == []
    health = source.health_check()
    assert health.status == SourceHealthStatus.PARTIAL
    assert health.errors


def test_max_queries_per_run_caps_search_calls():
    people = [
        PersonRef(person_id=uuid.uuid4(), canonical_name=f"Person {i}") for i in range(5)
    ]
    with patch("intelligence.ingestion.adapters.web_search._tavily_search", return_value=[]) as mock_search:
        source = WebSearchSource(api_key="test-key", max_queries_per_run=2)
        source.update_known_entities(people=people, as_of=AS_OF)
    assert mock_search.call_count == 2
