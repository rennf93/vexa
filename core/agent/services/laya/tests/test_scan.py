"""The scan wire: windowing rule, laya.v1 response shape, threshold/top_k, faults."""
import pytest


def test_scan_returns_candidates_best_first(client, fake_judge):
    body = {
        "transcript": [
            {"ts": "00:00:01", "speaker": "A", "text": "hello"},
            {"ts": "00:00:07", "speaker": "B", "text": "so we agreed, shipping Friday"},
            {"ts": "00:00:12", "speaker": "A", "text": "deal"},
        ],
        "language": "en",
    }
    r = client.post("/v1/scan/decision", json=body)
    assert r.status_code == 200
    data = r.json()
    assert data["window_count"] >= 1
    assert data["language"] == "en"
    assert data["checkpoint"] == "fake-ckpt"
    for c in data["candidates"]:
        assert set(c) == {"start_ts", "end_ts", "score", "text"}
        assert 0.0 <= c["score"] <= 1.0
    scores = [c["score"] for c in data["candidates"]]
    assert scores == sorted(scores, reverse=True)


def test_scan_below_threshold_yields_no_candidates(client, fake_judge):
    fake_judge.score = 0.05
    r = client.post(
        "/v1/scan/decision",
        json={"transcript": [{"ts": "00:00:01", "text": "hello there"}]},
    )
    assert r.status_code == 200
    assert r.json()["candidates"] == []
    assert r.json()["window_count"] == 1


def test_scan_422_on_empty_transcript(client):
    r = client.post("/v1/scan/decision", json={"transcript": []})
    assert r.status_code == 422


def test_scan_503_translates_judge_faults():
    """The adapter's typed fault becomes a 503 with an attributable detail (P18)."""
    from fastapi.testclient import TestClient

    from laya_svc.judge import LayaJudgeError
    from laya_svc.main import create_app

    class BrokenJudge:
        loaded = True

        def __call__(self, text, questions):
            raise LayaJudgeError("kg-v03", RuntimeError("cuda exploded"))

    client = TestClient(create_app(judge=BrokenJudge(), checkpoint="kg-v03"))
    r = client.post(
        "/v1/scan/decision",
        json={"transcript": [{"ts": "00:00:01", "text": "hello"}]},
    )
    assert r.status_code == 503
    assert "laya judge failed" in r.json()["detail"]
    assert "kg-v03" in r.json()["detail"]


def test_window_rule_is_the_training_rule():
    from laya_svc.scanner import split_windows

    utts = [{"ts": f"00:00:{i:02d}", "text": "x" * 100} for i in range(5)]
    ws = split_windows(utts)
    # 3-utterance window = 3x100 + 2 join spaces; then the remaining 2.
    assert [len(w["text"]) for w in ws] == [302, 201]
    assert ws[0]["start_ts"] == "00:00:00" and ws[0]["end_ts"] == "00:00:02"
