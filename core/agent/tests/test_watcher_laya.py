"""Watcher pre-pass tests (ADR-0036 SEAM B, live-copilot lane)."""
from __future__ import annotations

import pytest

import pytest

import control_plane.transcription_watcher as w
from control_plane.laya_prepass import LayaPrepass


def _reset_module_caches():
    w._native.clear()
    w._resolve_miss_at.clear()


def _payload(meeting_id):
    # Only meeting_id matters to the arm thread - transcript content is the collector's (P23).
    return {"type": "transcription", "meeting_id": meeting_id, "segments": [
        {"text": "hi", "completed": True, "start": 0.0, "end": 1.0, "segment_id": "x"}]}


def _fresh_state():
    return ({}, {}, {})


class _FakeRedis:
    def __init__(self) -> None:
        self.kv: dict[str, str] = {}

    def get(self, key): return self.kv.get(key)
    def set(self, key, value, ex=None): self.kv[key] = value
    def expire(self, key, ttl): pass
    def delete(self, key): self.kv.pop(key, None)


class _FakeDispatcher:
    def __init__(self) -> None:
        self.invocations: list[dict] = []

    def dispatch(self, inv):
        self.invocations.append(inv)
        return f"unit-{len(self.invocations)}"


class _FakeLive:
    def __init__(self) -> None:
        self.by_uid: dict[str, dict] = {}

    def add(self, row): self.by_uid[row["session_uid"]] = row
    def drop(self, uid): self.by_uid.pop(uid, None)


def _prepass(score: float = 0.9) -> LayaPrepass:
    def scan(url, payload, timeout):
        return {"window_count": 10, "language": "en", "checkpoint": "kg-v03", "elapsed_ms": 500.0,
                "candidates": [{"start_ts": "00:00:00", "end_ts": "00:00:07", "score": score,
                                "text": "so we agreed, shipping Friday"}]}
    return LayaPrepass("http://laya:8400", scan_fn=scan)


def test_arm_without_prepass_brief_is_base(monkeypatch):
    _reset_module_caches()
    """No prepass configured: the brief is byte-identical to _BRIEF (the OSS default)."""
    _reset = w._native.clear()
    monkeypatch.setattr(w, "_resolve_native", lambda mid: ("aaa-aaaa-aaa", "google_meet"))
    r, disp, live = _FakeRedis(), _FakeDispatcher(), _FakeLive()
    state = _fresh_state()
    w._handle(r, disp, live, "u_live", _payload("42"), *state,
              prepass=None, prepass_annotated=set())
    w._arm(disp, "u_live", "42", "google_meet",
           prepass=None, annotated=set())
    assert disp.invocations[0]["start"]["entrypoint"]["inline"] == w._BRIEF


def test_arm_with_prepass_prepends_candidates_once(monkeypatch):
    _reset_module_caches()
    """First arm carries the laya block; the 30s keep-alive re-arm does NOT rescan."""
    w._native.clear()
    monkeypatch.setattr(w, "_resolve_native", lambda mid: ("aaa-aaaa-aaa", "google_meet"))
    prepass = _prepass()
    r, disp, live = _FakeRedis(), _FakeDispatcher(), _FakeLive()
    state = _fresh_state()
    annotated: set[str] = set()

    # a transcription batch flows through the watcher (the prepass remembers it)
    w._handle(r, disp, live, "u_live", _payload("42"), *state,
              prepass=prepass, prepass_annotated=annotated)

    w._arm(disp, "u_live", "42", "google_meet", prepass=prepass, annotated=annotated)
    inline = disp.invocations[0]["start"]["entrypoint"]["inline"]
    assert inline.startswith(w._BRIEF)
    assert "Laya decision candidates" in inline
    assert "kg-v03" in inline

    # keep-alive re-arm: same brief, no second scan (the annotated set is the budget)
    calls = {"n": 0}
    real_scan = prepass._scan_fn
    def counting(url, payload, timeout):
        calls["n"] += 1
        return real_scan(url, payload, timeout)
    prepass._scan_fn = counting
    real_monotonic = w.time.monotonic
    monkeypatch.setattr(w.time, "monotonic", lambda: real_monotonic() + w.REARM_SEC + 1)
    r.set(f"proc:meeting:42:on", "1")
    w._handle(r, disp, live, "u_live", _payload("42"), *state,
              prepass=prepass, prepass_annotated=annotated)
    assert calls["n"] == 0


def test_peek_does_not_consume_memory():
    """The arm PEEKS so the fold-time scan (the bridge's own prepass) keeps the
    full history - a peek must leave the buffer intact."""
    prepass = _prepass()
    prepass.remember("s1", [{"start": 1.0, "speaker": "A", "text": "hello"}])
    first = prepass.annotate_peek("s1")
    second = prepass.annotate_peek("s1")
    assert first is not None and second is not None


def test_fail_soft_peek_returns_none(monkeypatch):
    def broken(url, payload, timeout):
        raise TimeoutError("laya down")

    prepass = LayaPrepass("http://laya:8400", scan_fn=broken)
    prepass.remember("s1", [{"start": 1.0, "speaker": "A", "text": "hello"}])
    assert prepass.annotate_peek("s1") is None
