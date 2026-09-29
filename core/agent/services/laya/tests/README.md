# tests — L1/L2 pyramid for the laya service

No torch, no checkpoint: the judge port is faked in conftest (P5 — that is WHY
the judge is a port). `test_health.py` pins the health contract;
`test_scan.py` pins windowing + the laya.v1 response shape. Checkpoint-loading
behavior is L3+ (compose volume + a real head), covered by the dogfood runbook
in PLAN.md, not here.
