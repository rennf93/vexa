# laya.v1 — the System-1 decision-scan wire (UNSEALED)

Request/response for `POST /v1/scan/decision` on the laya service
(`core/agent/services/laya`): a speaker-attributed transcript in, scored
decision-candidate windows out. The judge (which model head, how it loads) is
opaque behind this contract; provenance rides the response (`checkpoint`,
`elapsed_ms`) so callers attribute scans (P21). Consumers today: agent-api's
dispatch pre-pass (SEAM B). The MCP `laya_decide` tool surface is a separate
attachment (tools-seed descriptor), not this contract.

**Status: UNSEALED** — sealed with goldens when the pre-pass PR lands.
`gate:schema` validates its golden.
