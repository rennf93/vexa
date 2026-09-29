# laya — the System-1 decision service (agent lane)

A fast local classifier server: one laya checkpoint (e.g. `kg-v03`), two surfaces
off one load — `POST /v1/scan/decision` (laya.v1: transcript in, scored
decision-candidate windows out; consumed by agent-api's dispatch pre-pass) and
the `laya_decide` MCP tool at `/mcp` (consumed by dispatched agents through the
tools-seed descriptor `core/agent/tools-seed/laya_decide.json`). The judge is
non-generative: typed answers with probabilities in a single forward pass, so
there is nothing to parse and nothing to hallucinate.

**Config (env, validated in config.v1.json / P14):** `PORT` (8400), `HOST`,
`LOG_LEVEL`, `LAYA_CHECKPOINT` (local dir or HF repo id — required, fail-fast),
`LAYA_DEVICE`, `LAYA_SCAN_THRESHOLD` (0.3), `LAYA_SCAN_TOP_K` (12), `VEXA_ENV`.

**Deps (P17):** fastapi/uvicorn/pydantic (Cat A); the `laya` package
(Apache-2.0) + torch arrive via the `runtime` extra; `fastmcp` (MIT) via `mcp`.
The checkpoint ships as a mounted volume or an HF pull — never in git.

**Why a service (P10):** a 1.2GB torch runtime must not live in the control
plane, and worker containers need to reach it on the compose network (SEAM A).

Depends on: nothing in the graph — it loads a checkpoint and answers.
Consumed by: agent-api (pre-pass, `VEXA_LAYA_URL`), agent workers (MCP grant).
