"""judge.py — the checkpoint adapter: laya Agent -> the scanner's judge port.

Lazy-loads the checkpoint on first use (a 1.2GB torch load must not happen at
import, or every unit test pays it); single-threaded inference under a lock —
one forward pass at a time is what a single CPU/GPU agent wants. Faults are
translated HERE into a typed error (P18): callers see LayaJudgeError with the
checkpoint id, never a raw torch traceback.
"""
from __future__ import annotations

import threading
from typing import Any


class LayaJudgeError(RuntimeError):
    """A translated judge fault (load or inference) — carries the checkpoint id."""

    def __init__(self, checkpoint: str, cause: Exception) -> None:
        super().__init__(f"laya judge failed (checkpoint={checkpoint}): {cause}")
        self.checkpoint = checkpoint
        self.cause = cause


class LayaJudge:
    """Adapter around ``laya.agent.Agent`` — the ONLY module that imports torch-
    land. Unit tests never construct this; they pass a fake callable instead."""

    def __init__(self, checkpoint: str, device: str | None = None) -> None:
        self.checkpoint = checkpoint
        self.device = device
        self._agent: Any = None
        self._lock = threading.Lock()

    def _load(self) -> Any:
        if self._agent is None:
            with self._lock:
                if self._agent is None:
                    try:
                        from laya.agent import Agent  # heavy import, deferred
                    except Exception as e:  # noqa: BLE001 — translated below (P18)
                        raise LayaJudgeError(self.checkpoint, e) from e
                    try:
                        self._agent = Agent(self.checkpoint, device=self.device)
                    except Exception as e:  # noqa: BLE001
                        raise LayaJudgeError(self.checkpoint, e) from e
        return self._agent

    @property
    def loaded(self) -> bool:
        return self._agent is not None

    def __call__(self, text: str, questions: dict[str, Any]) -> dict[str, Any]:
        try:
            agent = self._load()
            return agent.predict({"body": text}, questions)
        except LayaJudgeError:
            raise
        except Exception as e:  # noqa: BLE001 — translated below (P18)
            raise LayaJudgeError(self.checkpoint, e) from e
