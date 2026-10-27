# Evidence status

What each checked-in result file is, so nothing is mistaken for a completed experiment.
Files are preserved as found; nothing was deleted or edited to produce this table.

| Path | What it is | Cloud-verified? |
|---|---|---|
| `reports/benchmark_results.jsonl`, `reports/evidence/run-*.json` | Two schema-v1 records (C02, E01) that ended as **environment failures before any computer was allocated** (`celesto_core` missing). | No (no run happened) |
| `reports/reliability_partial.json` | Summary of those two environment failures. | No |
| `reports/reliability.json` | A 20-run summary with 100% success from an earlier session. Its runs carry no `run_id`, and the current ledger has no matching records, so its provenance **cannot be reconstructed from this checkout**. Treat as unverified. | Unverified |
| `reports/reliability_consolidated.json` | Aggregation of earlier per-scenario evidence for 7 scenarios; verdict names (`date_bug_candidate`) predate the current `date_bug` vocabulary. | Unverified |
| `reports/rule_consistency.json` | Consistency check of earlier verdicts against hand-written rules. | Unverified |
| `reports/local_*.jsonl`, `reports/smoke1.jsonl` | **Local** runs with a patched Python clock (`execution_mode: local_python_clock_patch`). Not Celesto. | No (local only) |
| `reports/lifecycle.json`, `reports/failure_policy.json`, `reports/failure_trace.jsonl` | Mocked control-flow tests; the files state that no cloud guest was used. | No |
| `reports/containment.json`, `logs/containment.jsonl` | One host-side check that `rm -rf /` is blocked by the adapter guard. Does not test guest isolation. | No |
| `reports/concurrency.json` | Local thread-pool test; no Celesto guests. | No |
| `reports/api_smoke.json` | Smoke test against a local JSONL backend; PostgreSQL not tested. | No |
| `reports/postmortem.md` | Narrative of an earlier Docker Compose/PostgreSQL validation. The current `Dockerfile` did not include `api/` before this change, so that run cannot be reproduced from the prior checkout. | Unverified |
| `logs/commands.jsonl` | Command audit log from earlier sessions (1,278 lines). Evidence that commands were issued, not of their results. | n/a |
| **Root** `reliability.json`, `lifecycle.json`, `containment.json`, `failure_policy.json`, `failure_trace.jsonl`, `commands.jsonl`, `concurrency.json`, `capabilities.json`, `problem.json`, `manifest.json`, `feasibility.md`, `postmortem.md` | **Scaffold/placeholder files** created with the original project skeleton. Their numbers (e.g. root `reliability.json`: two runs, 12.5 s / 14.0 s, `sbx-fresh01/02`) match the formulas in the mock `BenchmarkRunner` in `timefault.py`, not measured runs. Root `failure_trace.jsonl` is a hand-written trace, and root `containment.json` asserts a block that no checked-in test demonstrates. They exist because `test_reports.py` checks their schema. **Do not cite them as results.** | No |

New harnesses (`agent/recovery.py`, `agent/concurrent_sandboxes.py`, `agent/evaluate.py`) write only to **new** files in `reports/` and label their `execution_mode`.
