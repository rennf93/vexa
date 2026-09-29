"""Health contract: 503 until the checkpoint is loaded, 200 + service id after (P18/P21)."""
from laya_svc.main import create_app


def test_health_503_when_checkpoint_unloaded():
    app = create_app(judge=FakeUnloaded(), checkpoint="kg-v03")
    client = _client(app)
    r = client.get("/health")
    assert r.status_code == 503
    body = r.json()
    assert body["status"] == "unhealthy"
    assert body["service"] == "laya"
    assert body["loaded"] is False


def test_health_200_when_loaded(client):
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "healthy"
    assert body["checkpoint"] == "fake-ckpt"


def test_root_reports_service_info(client):
    body = client.get("/").json()
    assert body["service"] == "Vexa Laya Service"
    assert body["endpoints"]["scan"] == "/v1/scan/decision"
    assert body["endpoints"]["health"] == "/health"


class FakeUnloaded:
    loaded = False

    def __call__(self, text, questions):  # pragma: no cover - never reached while unloaded
        raise AssertionError("judge called while unloaded")


def _client(app):
    from fastapi.testclient import TestClient

    return TestClient(app)
