"""laya_prepass.py — the SEAM B pre-pass (ADR-0036).

Remembers transcript segments as they flow through the bridge's egress (the
payloads were already crossing; remembering is a bounded side-eye, not a new
read path) and, when a ``session_end`` fires a meeting.completed run, asks the
laya service for decision-candidate windows. The annotation is ADVISORY: it
rides the spawn env into the worker, which materializes it as a workspace file
the fold agent may read — laya proposes, the agent verifies, the human approves.

Fail-soft BY CONSTRUCTION: every laya fault (down, slow, 5xx) returns None and
the dispatch proceeds exactly as without laya — the capability is optional
(``settings.laya_url`` empty ⇒ the prepass does not exist). Faults are typed
and logged (P18) but never crash the bridge.
"""
from __future__ import annotations

import json
import logging
import time
import urllib.request
from collections import OrderedDict
from typing import Any, Callable

logger = logging.getLogger("agent_api.laya")

LAYA_TIMEOUT_SEC = 60.0
MAX_SESSIONS = 64          # LRU over concurrent sessions
MAX_SEGMENTS = 600         # ~2h of dense talk; the scan windows to its own budget


class LayaPrepass:
    """Bounded per-session transcript memory + a fail-soft scan on session end.

    ``scan_fn`` is the port (P5): ``(url, payload, timeout) -> dict`` in prod
    (an HTTP adapter below), a fake in tests. State is in-memory by design —
    a bridge restart mid-meeting loses the pre-pass, never the meeting.
    """

    def __init__(
        self,
        laya_url: str,
        scan_fn: Callable[[str, dict[str, Any], float], dict[str, Any]] | None = None,
        threshold: float = 0.3,
        top_k: int = 12,
    ) -> None:
        self._url = laya_url.rstrip("/")
        self._scan_fn = scan_fn or _http_scan
        self._threshold = threshold
        self._top_k = top_k
        self._sessions: OrderedDict[str, list[dict[str, str]]] = OrderedDict()

    def remember(self, session_uid: str, segments: list[dict[str, Any]]) -> None:
        """Accumulate a transcription batch's segments for this session."""
        if not segments:
            return
        buf = self._sessions.get(session_uid)
        if buf is None:
            if len(self._sessions) >= MAX_SESSIONS:
                self._sessions.popitem(last=False)  # evict the least-recent session
            buf = []
            self._sessions[session_uid] = buf
        self._sessions.move_to_end(session_uid)
        for seg in segments:
            text = str(seg.get("text") or "").strip()
            if not text:
                continue
            buf.append(
                {
                    "ts": _fmt_ts(seg.get("start")),
                    "speaker": str(seg.get("speaker") or ""),
                    "text": text,
                }
            )
        if len(buf) > MAX_SEGMENTS:
            del buf[: len(buf) - MAX_SEGMENTS]

    def annotate_on_end(self, session_uid: str) -> dict[str, Any] | None:
        """Scan the session's transcript for decision candidates. Returns
        ``{"block": markdown, "result": laya.v1 response}`` or None (no memory,
        no candidates, or ANY fault — logged typed, never raised)."""
        segs = self._sessions.pop(session_uid, None)
        if not segs:
            return None
        try:
            result = self._scan_fn(
                self._url,
                {
                    "transcript": [
                        {"ts": s["ts"], "speaker": s["speaker"], "text": s["text"]}
                        for s in segs
                    ],
                    "threshold": self._threshold,
                    "top_k": self._top_k,
                },
                LAYA_TIMEOUT_SEC,
            )
        except Exception as e:  # noqa: BLE001 — fail-soft is the CONTRACT here (P18)
            logger.error("laya prepass scan fault (session=%s): %s", session_uid, e)
            return None
        if not result.get("candidates"):
            logger.info("laya prepass: no candidates (session=%s, windows=%s)",
                        session_uid, result.get("window_count"))
            return None
        logger.info(
            "laya prepass scan (session=%s): %s candidates / %s windows / %s ms / checkpoint=%s",
            session_uid, len(result["candidates"]), result.get("window_count"),
            result.get("elapsed_ms"), result.get("checkpoint"),
        )
        return {"block": annotation_block(result), "result": result}


def _fmt_ts(start: Any) -> str:
    """Segment start -> a displayable ts. Numbers (seconds) -> HH:MM:SS; pass
    strings through untouched."""
    if isinstance(start, (int, float)):
        s = int(start)
        return f"{s // 3600:02d}:{(s % 3600) // 60:02d}:{s % 60:02d}"
    return str(start or "00:00:00")


def _http_scan(url: str, payload: dict[str, Any], timeout: float) -> dict[str, Any]:
    req = urllib.request.Request(
        f"{url}/v1/scan/decision",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310 — internal service
        return json.load(r)


def annotation_block(result: dict[str, Any]) -> str:
    """Render the advisory block the worker materializes into the workspace."""
    lines = [
        "## Laya decision candidates (System-1 scan)",
        "",
        f"Source: `{result.get('checkpoint')}` scored {result.get('window_count')} windows; "
        f"{len(result.get('candidates', []))} scored >= threshold. These are HINTS, ranked by "
        "P(decision) — verify each against the transcript before relying on it, and read the "
        "transcript regardless: absence from this list is NOT absence of a decision.",
        "",
    ]
    for c in result.get("candidates", []):
        text = " ".join(str(c.get("text", "")).split())
        if len(text) > 220:
            text = text[:217] + "..."
        lines.append(f"- `{c.get('start_ts')}-{c.get('end_ts')}` ({c.get('score'):.2f}) {text}")
    return "\n".join(lines)
