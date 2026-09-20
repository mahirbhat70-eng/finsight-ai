"""Phase 0 acceptance: /api/v1/health returns the contract shape.

Unit-level test (no db): the route exists and returns a JSON body with the
required keys. The full {status, db, redis, version} check against the
compose stack is the playbook acceptance curl.
"""

from fastapi.testclient import TestClient

from app.main import app


def test_health_contract_shape() -> None:
    client = TestClient(app)
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    body = resp.json()
    for key in ("status", "db", "redis", "version"):
        assert key in body, f"missing {key} in health payload"
    assert body["status"] in {"ok", "degraded"}


def test_error_envelope_shape() -> None:
    from app.core.errors import AppError

    @app.get("/api/v1/_boom")
    async def _boom() -> None:
        raise AppError("test_error", "boom", status_code=422)

    client = TestClient(app, raise_server_exceptions=False)
    resp = client.get("/api/v1/_boom")
    assert resp.status_code == 422
    err = resp.json()["error"]
    assert {"code", "message", "request_id"} <= set(err)
