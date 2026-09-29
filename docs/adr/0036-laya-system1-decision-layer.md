# ADR-0036: Laya — a System-1 decision layer beside the dispatched agent

Date: 2026-09-29
Status: Accepted (fork-local implementation; upstream PR is a separate, human-gated decision)

## Context

Agent lane work (folding a meeting transcript into a workspace's knowledge
graph) is done by a dispatched agent — a generative LLM. Measured on real
deployment data, a small non-generative classifier head (the `laya` checkpoint,
`kg-v03`) detects "this window contains a decision" at 0.995 with the true
decision moment ranked first, while the same head zero-shot was near chance;
the head is ~125 ms per window on CPU. Generative tokens are the wrong currency
for thousands of yes/no judgments per fold.

## Decision

Add a **laya service** to the agent domain: one checkpoint, two surfaces.

1. **SEAM A — a tool, not a prompt.** `core/agent/tools-seed/laya_decide.json`
   (the FIRST resident of the descriptor registry) grants dispatched agents a
   `laya_decide` MCP tool: typed-decision judgments (choice/score/noul) in one
   forward pass. Questions live caller-side (workspace templates), byte-pinned;
   the service only judges — mechanism, not policy (P11).
2. **SEAM B — a pre-pass, fail-soft by construction.** When `VEXA_LAYA_URL` is
   set, agent-api annotates a meeting transcript at dispatch time (language from
   transcript.v1's own per-segment field; decision-candidate windows from
   laya.v1 `/v1/scan/decision`) and hands the agent the triaged map. Empty URL =
   the pre-pass is ABSENT, not degraded (P14 capability conventions).

## Trade-offs accepted

- **A new runtime** (P10 tax): a 1.2GB torch checkpoint must not live in the
  control plane, and worker containers need it on the compose network — the
  distribution force is the same one that carved the transcription worker.
- **A non-deterministic component in the knowledge path** is bounded by role:
  laya proposes and *logs* (every call is a wire-format line); the dispatched
  agent verifies against the transcript; human approval gates workspace
  commits (P20 unchanged). Promotions from advisory to gating are pre-registered
  acceptance decisions, made on recorded evidence, per touchpoint.
- **Checkpoint distribution stays out of the repo**: weights mount by volume or
  pull from an approved HF repo (gate:licenses records baked weights in the
  SBOM; volumes keep images small and publishing a separate, human decision).
- **English-only head v1**: non-English transcripts skip laya via
  transcript.v1's own per-segment `language` field — the gate needs no new
  detection code. Multilingual heads are a trained-data question, not an
  architecture one.

## Consequences

- `core/agent/contracts/laya.v1` (UNSEALED) + goldens pin the scan wire (P4/P8).
- Every laya call is attributable (checkpoint id + elapsed in the response;
  P18/P21), and the call stream doubles as the labeled-training-set collector
  for successor heads.
- CALM: the `laya` service and `laya.v1` contract join the agent domain
  (architecture.calm.json); `pnpm seal:arch` re-stamps the baseline with this
  ADR referenced (gate:dataflow).
