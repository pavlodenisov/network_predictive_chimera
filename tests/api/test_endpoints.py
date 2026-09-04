"""API surface smoke tests (spec §42-43) against a small in-transaction universe."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from intelligence.facts import FactType
from tests.factories import add_edge, add_event, add_fact, dt, make_person, seed_sample_thesis

AS_OF = dt(2026, 9, 6)


@pytest.fixture
def populated(session):
    """Seed a couple of people + one weekly run so ranking/digest endpoints have data."""
    from intelligence.jobs.pipeline import run_weekly

    seed_sample_thesis(session)
    # a source + the live adapters expect rows; add the synthetic source disabled so the
    # pipeline's Stage 1 finds nothing external but still runs.
    p = make_person(session, "Sarah Chen")
    add_fact(session, p, FactType.HEADLINE_TEXT, "inference infrastructure")
    add_fact(session, p, FactType.YEARS_DOMAIN_EXPERIENCE, 5.4, unit="years")
    add_fact(session, p, FactType.PRIOR_FOUNDER, True)
    add_event(session, p, "EMPLOYMENT_ENDED", occurred_at=dt(2026, 8, 31))
    chimera = make_person(session, "Chimera Person", chimera_seed=True)
    add_edge(session, chimera, p, strength="MODERATE")
    run_weekly(session, as_of=dt(2026, 9, 6).date(), code_version="apitest")
    session.commit()
    return p


def test_health(client: TestClient):
    assert client.get("/health").json()["status"] == "ok"


def test_people_list_and_detail(client: TestClient, populated):
    r = client.get("/people", params={"q": "Sarah"})
    assert r.status_code == 200
    body = r.json()
    assert body["total"] >= 1
    row = body["items"][0]
    assert row["name"] == "Sarah Chen"
    assert "scores" in row

    pid = row["id"]
    detail = client.get(f"/people/{pid}").json()
    assert detail["name"] == "Sarah Chen"
    assert isinstance(detail["classes"], list)
    assert "founder" in detail["scores"]
    fs = detail["scores"]["founder"]
    assert 0.0 <= fs["confidence"] <= 1.0
    assert fs["confidence"] != fs["priority"]  # separate (spec §18)
    assert detail["strongest_path"] is not None


def test_person_drilldown_chain(client: TestClient, populated):
    pid = client.get("/people", params={"q": "Sarah"}).json()["items"][0]["id"]

    facts = client.get(f"/people/{pid}/facts").json()["items"]
    assert facts
    fact_with_ev = next(f for f in facts if f["evidence"])
    ev = fact_with_ev["evidence"][0]
    assert ev["observation"] is not None  # fact -> evidence -> immutable observation

    scores = client.get(f"/people/{pid}/scores").json()["items"]
    assert scores
    founder = next(s for s in scores if s["model"] == "founder")
    dims = founder["contribution_breakdown"]["dimensions"]
    recomputed = sum(d["weighted"] for d in dims.values())
    assert abs(recomputed - founder["priority_score"]) < 0.1

    feats = client.get(f"/people/{pid}/features").json()["items"]
    assert feats
    assert "missing_features" in feats[0]

    paths = client.get(f"/people/{pid}/paths").json()
    assert paths["status"] in {"known", "unknown"}


def test_rankings(client: TestClient, populated):
    r = client.get("/rankings/founders")
    assert r.status_code == 200
    body = r.json()
    assert body["model_target"] == "founder"
    assert "universe" in body
    assert any(i["name"] == "Sarah Chen" for i in body["items"])


def test_events_and_search(client: TestClient, populated):
    ev = client.get("/events", params={"event_type": "EMPLOYMENT_ENDED"}).json()
    assert ev["total"] >= 1
    assert ev["items"][0]["person"] == "Sarah Chen"

    s = client.get("/search", params={"q": "Sarah"}).json()
    assert any(p["name"] == "Sarah Chen" for p in s["people"])


def test_models_and_weekly_runs(client: TestClient, populated):
    models = client.get("/models").json()["items"]
    names = {m["name"] for m in models}
    assert {"founder", "lp", "talent", "connector"} <= names
    founder = next(m for m in models if m["name"] == "founder")
    assert abs(sum(founder["dimension_weights"].values()) - 1.0) < 1e-6

    runs = client.get("/weekly-runs").json()["items"]
    assert runs
    detail = client.get(f"/weekly-runs/{runs[0]['id']}").json()
    assert "digest" in detail and "stage_stats" in detail


def test_data_quality(client: TestClient, populated):
    dq = client.get("/data-quality").json()
    assert "source_failures" in dq
    assert "extraction_failures" in dq
    assert "suspicious_duplicate_names" in dq


def test_feedback_write(client: TestClient, populated):
    pid = client.get("/people", params={"q": "Sarah"}).json()["items"][0]["id"]
    r = client.post("/feedback", json={"person_id": pid, "feedback_type": "CONTACT_NOW"})
    assert r.status_code == 201
    assert "id" in r.json()
