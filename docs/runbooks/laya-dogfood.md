# Dogfood runbook — laya on a live stack

One-time setup on the machine that runs the compose stack (Renzo's NAS), then
every meeting proves it. All steps local; pushing/publishing is gated.

## 0. Prereqs

- The stack compose file includes the `laya` service (profile `laya`) and the
  agent-api env `VEXA_LAYA_URL` (both landed in
  `deploy/compose/docker-compose.yml` + `.env.example`).
- The checkpoint exists on that host: `model.safetensors` +
  `rl_agent_config.json` + `tokenizer/` (kg-v03; on the Mac dev box:
  `~/colibri/checkpoints/kg-v03`).

## 1. Mount the checkpoint + enable the profile

In `deploy/compose/.env`:

```
LAYA_CHECKPOINT_HOST=/absolute/path/to/kg-v03   # e.g. /home/renzo/colibri/checkpoints/kg-v03
LAYA_DEVICE=                                     # empty = auto
COMPOSE_PROFILES=laya                            # adds the laya service to `up`
VEXA_LAYA_URL=http://laya:8400                   # the agent-api pre-pass switch
```

Bring it up: `docker compose up -d laya agent-api`

## 2. Watch it come up honestly (P18/P21)

- `docker compose logs -f laya` — first decision-scan loads the checkpoint
  (torch, tens of seconds). `/health` is 503 `unhealthy` until loaded, then 200.
- A WRONG checkpoint path = the container exits fast and loud (by design);
  `docker ps` shows the restart loop — fix the path, don't fight it.

## 3. Prove the scan wire without a meeting

```
curl -s http://localhost:8400/v1/scan/decision -H 'Content-Type: application/json' \
  -d '{"transcript":[{"ts":"00:00:01","speaker":"A","text":"so we agreed, we ship Friday"}]}'
# expect: candidates with a high score + "checkpoint":"kg-v03"
```

## 4. Run one real meeting

Any meeting on the stack (bot, bridge, calendar). After it ends:

1. The agent-api logs show one line: `laya prepass scan (session=…): N candidates…`
   (or `no candidates` — both are success; a FAULT line is the thing to fix).
2. The agent worker's workspace contains `.laya/meeting-scan.md` with the same
   ranked candidates (never committed — same rule as `.claude/`).
3. The fold output cites the candidate moments where they were real decisions,
   and the human spot-check finds no decision the scan MISSED that the fold also
   missed (recall is the agent's job; laya only orders the reading).

## 5. Prove SEAM A (the agent tool)

In any dispatched agent session with `unit.v1.tools` including `laya_decide`
(meeting copilots get it from the descriptor once the grant wiring is enabled):

- Ask the agent: "use laya_decide to check whether this passage contains a
  decision: <paste 2-3 utterances>".
- Expect a typed answer with probabilities + `checkpoint: kg-v03` in the tool
  result, in about 0.1-0.5s.

## 6. Kill switches

- Per meeting: nothing to do — the pre-pass only annotates.
- Per deployment: `VEXA_LAYA_URL=` (empty) + `docker compose up -d agent-api`
  → no laya calls anywhere, transcripts dispatch exactly as before.
- Whole service: drop `laya` from `COMPOSE_PROFILES`.

## 7. What to collect for the next head

Every pre-pass scan is the training set for kg-v04 (wire format + score +
the fold's actual decisions = labels). Keep `docker compose logs agent-api`
around, or scrape the scans into the sft/ dataset dir.
