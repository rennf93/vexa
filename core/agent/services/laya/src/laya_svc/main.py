"""main.py — the laya service composition root.

One concern: fast, local System-1 judgment for the agent lane. Two surfaces off
one loaded checkpoint: POST /v1/scan/decision (laya.v1 — consumed by agent-api's
dispatch pre-pass) and the `laya_decide` MCP tool at /mcp (consumed by
dispatched agents via tools-seed). The judge adapter is injected at the
composition root; unit tests pass a fake (P5/P19 — no torch in the pyramid).

Config is a validated contract delivered by env (P14): PORT, HOST, LOG_LEVEL,
LAYA_CHECKPOINT (a local dir or an HF repo id), LAYA_DEVICE, LAYA_SCAN_THRESHOLD,
LAYA_SCAN_TOP_K — declared in config.v1.json.
"""
from __future__ import annotations

import logging
import os
from typing import Any

from fastapi import FastAPI, HTTPException

from laya_svc.judge import LayaJudge, LayaJudgeError
from laya_svc.scanner import DEFAULT_THRESHOLD, DEFAULT_TOP_K, scan_windows

logger = logging.getLogger("agent_api.laya")

SERVICE_NAME = "laya"

PORT = int(os.getenv("PORT", "8400"))
HOST = os.getenv("HOST", "0.0.0.0")
LOG_LEVEL = os.getenv("LOG_LEVEL", "info")
LAYA_CHECKPOINT = os.getenv("LAYA_CHECKPOINT", "")
LAYA_DEVICE = os.getenv("LAYA_DEVICE") or None
LAYA_SCAN_THRESHOLD = float(os.getenv("LAYA_SCAN_THRESHOLD", str(DEFAULT_THRESHOLD)))
LAYA_SCAN_TOP_K = int(os.getenv("LAYA_SCAN_TOP_K", str(DEFAULT_TOP_K)))
VEXA_ENV = os.getenv("VEXA_ENV", "development")

logging.basicConfig(level=getattr(logging, LOG_LEVEL.upper(), logging.INFO))


def create_app(judge: Any = None, checkpoint: str | None = None) -> FastAPI:
    """Composition root. ``judge`` overrides the checkpoint adapter (tests pass
    a fake; prod leaves None -> LayaJudge(LAYA_CHECKPOINT))."""
    checkpoint_id = checkpoint or (LAYA_CHECKPOINT.rsplit("/", 1)[-1] or "unset")
    if judge is None:
        if not LAYA_CHECKPOINT:
            raise RuntimeError(
                "LAYA_CHECKPOINT is required (a local checkpoint dir or an HF "
                "repo id) — set it in compose/.env; the service refuses to "
                "start pointlessly (P14: validate at boot, fail fast)."
            )
        judge = LayaJudge(LAYA_CHECKPOINT, device=LAYA_DEVICE)

    docs = VEXA_ENV != "production"
    app = FastAPI(
        title="Vexa Laya Service",
        version="0.1.0",
        docs_url="/docs" if docs else None,
        redoc_url="/redoc" if docs else None,
        openapi_url="/openapi.json" if docs else None,
    )
    app.state.judge = judge
    app.state.checkpoint = checkpoint_id

    @app.get("/health")
    def health() -> Any:
        # P18: /health reports the dependency truth. Until the checkpoint has
        # actually loaded we are 503 "loading" — never a fake green (P21).
        loaded = getattr(judge, "loaded", True)
        from fastapi.responses import JSONResponse

        return JSONResponse(
            {
                "status": "healthy" if loaded else "unhealthy",
                "service": SERVICE_NAME,
                "checkpoint": checkpoint_id,
                "loaded": loaded,
            },
            status_code=200 if loaded else 503,
        )

    @app.get("/")
    def root() -> dict[str, Any]:
        return {
            "service": "Vexa Laya Service",
            "endpoints": {"scan": "/v1/scan/decision", "health": "/health", "mcp": "/mcp"},
        }

    @app.post("/v1/scan/decision")
    def scan_decision(body: dict[str, Any]) -> dict[str, Any]:
        utts = [
            {"ts": str(u.get("ts", "")), "text": str(u.get("text", ""))}
            for u in (body.get("transcript") or [])
            if str(u.get("text", "")).strip()
        ]
        if not utts:
            raise HTTPException(status_code=422, detail="transcript must have utterances with text")
        try:
            result = scan_windows(
                judge,
                utts,
                threshold=float(body.get("threshold", LAYA_SCAN_THRESHOLD)),
                top_k=int(body.get("top_k", LAYA_SCAN_TOP_K)),
            )
        except LayaJudgeError as e:
            logger.error("laya scan fault: %s", e)  # typed fault, loud (P18)
            raise HTTPException(status_code=503, detail=str(e)) from e
        return {
            "window_count": result["window_count"],
            "candidates": result["candidates"],
            "language": body.get("language"),
            "checkpoint": checkpoint_id,
            "elapsed_ms": result["elapsed_ms"],
        }

    # SEAM A surface — optional extra; absence is typed, loud at startup (P18).
    try:
        from laya_svc.mcp_tools import build_mcp_app
    except ImportError as e:  # pragma: no cover - depends on extras
        logger.warning("MCP surface unavailable: %s", e)
    else:
        try:
            mcp_app = build_mcp_app(judge, checkpoint_id)
            app.mount("/mcp", mcp_app)
        except Exception as e:  # noqa: BLE001 — typed startup warning (P18)
            logger.warning("MCP surface failed to build: %s", e)

    return app


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "laya_svc.main:app", host=HOST, port=PORT,
        log_level=LOG_LEVEL.lower(),
    )
