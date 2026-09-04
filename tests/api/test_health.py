from __future__ import annotations

from fastapi.testclient import TestClient


def test_health_ok(client: TestClient) -> None:
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["database"]["connected"] is True
    assert body["database"]["dialect"] == "sqlite"
    assert body["database"]["tables"] >= 30
    assert body["extraction"]["extractor"] == "rules"
    assert body["extraction"]["llm_available"] is False
