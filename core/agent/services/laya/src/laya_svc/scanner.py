"""scanner.py — decision-candidate windowing + aggregation over a judge port (P5).

The judge is a callable ``(text, questions) -> answers`` — the laya checkpoint
adapter (``judge.py``) in prod, an in-memory fake in tests (L2, P5/P19). The
byte-pinned scan questions live HERE (frozen at kg-v03 training time; never
reword mid-collection — train == serve).
"""
from __future__ import annotations

import time
from typing import Any, Callable

# BYTE-PINNED at kg-v03 training (sft/pilot_seed.py QUESTIONS.has_decision).
# Rewording these invalidates every checkpoint trained on them.
SCAN_QUESTIONS: dict[str, dict[str, Any]] = {
    "has_decision": {
        "type": "noul",
        "instructions": (
            "Does this passage of meeting transcript contain an explicit "
            "decision, agreement, or commitment to a course of action?"
        ),
        "criteria": {
            "true": (
                "someone explicitly decides, agrees, commits, proposes a "
                "concrete joint action, or accepts a proposal"
            ),
            "false": (
                "small talk, status update, description, question, or general "
                "discussion without commitment"
            ),
        },
    }
}

MAX_WINDOW_CHARS = 1200
MAX_WINDOW_UTTS = 3
DEFAULT_THRESHOLD = 0.3
DEFAULT_TOP_K = 12

Judge = Callable[[str, dict[str, Any]], dict[str, Any]]


def split_windows(
    utts: list[dict[str, str]],
    max_chars: int = MAX_WINDOW_CHARS,
    max_utts: int = MAX_WINDOW_UTTS,
) -> list[dict[str, str]]:
    """Group consecutive utterances into judge-sized windows: <= max_utts
    utterances and <= max_chars chars (the sizes every kg head was trained on)."""
    windows: list[dict[str, str]] = []
    i = 0
    while i < len(utts):
        texts = [utts[i]["text"]]
        j = i + 1
        while (
            j < len(utts)
            and len(texts) < max_utts
            and sum(len(t) for t in texts) + len(utts[j]["text"]) < max_chars
        ):
            texts.append(utts[j]["text"])
            j += 1
        windows.append(
            {
                "start_ts": utts[i]["ts"],
                "end_ts": utts[j - 1]["ts"],
                "text": " ".join(texts),
            }
        )
        i = j
    return windows


def scan_windows(
    judge: Judge,
    utts: list[dict[str, str]],
    threshold: float = DEFAULT_THRESHOLD,
    top_k: int = DEFAULT_TOP_K,
) -> dict[str, Any]:
    """Score every window with the judge, keep P(decision) >= threshold,
    best-first, trimmed to top_k. Raises whatever the judge raises — the
    adapter translates its own faults (P18); the caller decides policy."""
    windows = split_windows(utts)
    t0 = time.perf_counter()
    scored: list[dict[str, Any]] = []
    for w in windows:
        answers = judge(w["text"], SCAN_QUESTIONS)
        p = float(answers["answers"]["has_decision"]["noul"])
        if p >= threshold:
            scored.append(
                {
                    "start_ts": w["start_ts"],
                    "end_ts": w["end_ts"],
                    "score": round(p, 4),
                    "text": w["text"],
                }
            )
    scored.sort(key=lambda c: -c["score"])
    return {
        "window_count": len(windows),
        "candidates": scored[:top_k],
        "elapsed_ms": round((time.perf_counter() - t0) * 1000, 1),
    }
