"""laya prepass + bridge wiring tests (ADR-0036 SEAM B). The laya HTTP call is
faked at the scan port — no server, no torch (P5/P19)."""
from __future__ import annotations

import pytest

from control_plane.laya_prepass import LayaPrepass, annotation_block


def _fake_scan(score: float = 0.9, candidates: int = 2, windows: int = 50):
    def scan(url, payload, timeout):
        assert payload["transcript"], "scan must receive the remembered segments"
        return {
            "window_count": windows,
            "candidates": [
                {"start_ts": "00:42:41", "end_ts": "00:43:03", "score": score,
                 "text": "let's do it"} for _ in range(candidates)
            ],
            "language": "en", "checkpoint": "kg-v03", "elapsed_ms": 4100.0,
        }
    return scan


def test_remember_and_annotate_roundtrip():
    p = LayaPrepass("http://laya:8400", scan_fn=_fake_scan())
    p.remember("s1", [{"start": 2561.0, "speaker": "A", "text": "so we agreed, shipping Friday"},
                      {"start": "00:43:00", "speaker": "B", "text": "deal"}])
    out = p.annotate_on_end("s1")
    assert out is not None
    assert "kg-v03" in out["block"]
    assert "00:42:41" in out["block"]
    # second call: memory consumed — no double-annotate
    assert p.annotate_on_end("s1") is None


def test_fail_soft_on_scan_fault(caplog):
    def broken(url, payload, timeout):
        raise TimeoutError("laya down")

    p = LayaPrepass("http://laya:8400", scan_fn=broken)
    p.remember("s1", [{"start": 1.0, "text": "hello"}])
    assert p.annotate_on_end("s1") is None  # never raises — the contract


def test_annotate_none_without_memory():
    p = LayaPrepass("http://laya:8400", scan_fn=_fake_scan())
    assert p.annotate_on_end("ghost") is None


def test_bounded_memory_evicts_least_recent():
    p = LayaPrepass("http://laya:8400", scan_fn=_fake_scan())
    for i in range(64):
        p.remember(f"s{i}", [{"start": 1.0, "text": "x"}])
    p.remember("s0b", [{"start": 1.0, "text": "x"}])  # 65th session evicts s0
    assert p.annotate_on_end("s0") is None
    assert p.annotate_on_end("s1") is not None


def test_annotation_block_carries_the_advisory_contract():
    result = _fake_scan()("http://x", {"transcript": [{"ts": "00:42:41", "text": "let's do it"}]}, 1.0)
    block = annotation_block(result)
    assert "HINTS" in block
    assert "NOT absence of a decision" in block  # the recall caveat is the contract
    assert "kg-v03" in block


# ── bridge wiring ────────────────────────────────────────────────────────────

def test_bridge_injects_annotation_env(tmp_path, monkeypatch):
    """transcription batches feed the prepass; session_end scans and the spawn
    env carries VEXA_LAYA_ANNOTATION. Without laya_url: byte-identical bridge."""
    from shared.config import Settings
    import control_plane.bridge as bridge_mod
    from control_plane.bridge import TranscriptBridge

    class FakeRuntime:
        def __init__(self): self.envs = []
        def spawn(self, wid, profile, env): self.envs.append(env); return wid

    class FakeResolver:
        def __call__(self, meeting_id): return f"repo/{meeting_id}"

    settings = Settings(
        runtime_api_url="http://runtime-api:8090", workspace_mount_source="ws",
        laya_url="http://laya:8400",
    )
    rt = FakeRuntime()
    b = TranscriptBridge(settings, runtime=rt, resolver=FakeResolver())
    assert b.prepass is not None
    b.prepass._scan_fn = _fake_scan()  # the port: no live laya in the unit pyramid
    monkeypatch.setattr(bridge_mod, "build_worker_env",
                        lambda s, repo: {"BUILT_FOR": repo})

    segs = [{"segment_id": "x", "speaker": "A", "text": "let's ship it",
             "start": 2561.0, "end": 2563.0, "completed": True}]
    assert b.handle({"type": "transcription", "session_uid": "s1", "meeting_id": "s1",
                     "segments": segs}) is None
    wid = b.handle({"type": "session_end", "session_uid": "s1"})
    assert wid == "agent-s1"
    assert "VEXA_LAYA_ANNOTATION" in rt.envs[0]
    assert "kg-v03" in rt.envs[0]["VEXA_LAYA_ANNOTATION"]

    # a session the prepass never saw still dispatches, env untouched
    wid2 = b.handle({"type": "session_end", "session_uid": "ghost"})
    assert wid2 == "agent-ghost"
    assert "VEXA_LAYA_ANNOTATION" not in rt.envs[1]


def test_bridge_without_laya_url_has_no_prepass():
    from shared.config import Settings
    from control_plane.bridge import TranscriptBridge

    settings = Settings(runtime_api_url="http://runtime-api:8090")
    b = TranscriptBridge(settings, runtime=lambda *a: None, resolver=lambda m: m)
    assert b.prepass is None
