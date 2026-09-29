"""Worker-side SEAM A/B wiring (ADR-0036): annotation materialization + toolbelt grant.

The registry/descriptor half is config (tools-seed/*.json); these pin the code
half — the env in, the workspace file and the allowed list out."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from worker.engine import _resolve_toolbelt, _write_laya_annotation


def test_annotation_materialized_under_laya_dir(tmp_path: Path):
    from control_plane.laya_prepass import annotation_block

    block = annotation_block({
        "checkpoint": "kg-v03", "window_count": 50, "elapsed_ms": 4100.0,
        "candidates": [{"start_ts": "00:42:41", "end_ts": "00:43:03", "score": 0.99,
                        "text": "let's do it"}],
    })
    _write_laya_annotation(tmp_path, block)
    f = tmp_path / ".laya" / "meeting-scan.md"
    assert f.exists()
    assert "HINTS" in f.read_text() and "kg-v03" in f.read_text()


def test_annotation_write_failure_is_swallowed_logged(tmp_path: Path):
    # a FILE where the dir should be -> OSError -> advisory swallowed, never raised
    (tmp_path / ".laya").write_text("not a directory")
    _write_laya_annotation(tmp_path, "block")  # must not raise


def test_resolver_no_env_returns_defaults(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("VEXA_UNIT_TOOLS", raising=False)
    expected = (monkeypatch._original_backend if False else
                "Read,Write,Edit,Glob,Grep,Bash,WebSearch,WebFetch").split(",")
    assert _resolve_toolbelt(tmp_path) == expected


def test_resolver_unknown_names_fail_closed(tmp_path: Path, monkeypatch):
    seed = tmp_path / "seed"
    seed.mkdir()
    monkeypatch.setenv("VEXA_UNIT_TOOLS", "nonsense.tool")
    monkeypatch.setenv("VEXA_TOOLS_SEED_DIR", str(seed))
    allowed = _resolve_toolbelt(tmp_path)
    # fail-closed: unknown tool silently dropped, base tools remain
    assert allowed == ["Read", "Write", "Edit"]


def test_resolver_grants_laya_via_descriptor(tmp_path: Path, monkeypatch):
    """The tools-seed descriptor resolves into mcp__laya on the allow list and a
    .claude/mcp.json pointing at the laya service (SEAM A end-to-end, offline)."""
    seed = tmp_path / "seed"
    seed.mkdir()
    (seed / "laya_decide.json").write_text(json.dumps({
        "tool": {"name": "laya_decide", "scope": "laya:decide", "grant": "auto",
                 "transport": "mcp", "mcp_server": "laya"},
        "mcp": {"url": "http://laya:8400/mcp", "type": "http"},
    }))
    monkeypatch.setenv("VEXA_UNIT_TOOLS", "laya_decide")
    monkeypatch.setenv("VEXA_TOOLS_SEED_DIR", str(seed))

    ws = tmp_path / "ws"
    ws.mkdir()
    allowed = _resolve_toolbelt(ws)
    assert "mcp__laya" in allowed
    mcp = json.loads((ws / ".claude" / "mcp.json").read_text())
    assert mcp["mcpServers"]["laya"]["url"] == "http://laya:8400/mcp"
