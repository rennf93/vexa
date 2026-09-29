"""Fixtures: a fake judge (the port, P5) and an app under test with it."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from laya_svc.main import create_app


class FakeJudge:
    """In-memory judge: scores are deterministic, no torch. loaded mirrors the
    real adapter's lifecycle so /health's 503 path is exercisable."""

    def __init__(self, score: float = 0.95, loaded: bool = True) -> None:
        self.score = score
        self._loaded = loaded

    @property
    def loaded(self) -> bool:
        return self._loaded

    def __call__(self, text: str, questions: dict) -> dict:
        assert questions["has_decision"]["type"] == "noul"  # byte-pinned surface
        return {"answers": {"has_decision": {"noul": self.score}}}


@pytest.fixture()
def fake_judge() -> FakeJudge:
    return FakeJudge()


@pytest.fixture()
def client(fake_judge) -> TestClient:
    return TestClient(create_app(judge=fake_judge, checkpoint="fake-ckpt"))
