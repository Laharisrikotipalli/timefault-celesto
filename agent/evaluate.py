"""Aggregate a batch of cloud benchmark ledger records into an evaluation report.

Only schema_version>=2 records with execution_mode == celesto_cloud and fresh
computers count. The report status is "complete" only when the required number
of distinct, fresh, non-interrupted runs is present; otherwise it is
"incomplete" with reasons. This module never fabricates or imputes runs.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCHEMA = "evaluation_report.v1"
DATE_BUG_VERDICTS = frozenset({"date_bug", "date_bug_candidate"})


def wilson(successes: int, n: int, z: float = 1.96):
    if n == 0:
        return None
    p = successes / n
    d = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / d
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return [round(max(0.0, centre - half), 4), round(min(1.0, centre + half), 4)]


def _pct(values, q):
    v = sorted(values)
    return v[math.ceil(q * len(v)) - 1] if v else None


def load_ledger(path: Path) -> tuple[list[dict], int]:
    records, malformed = [], 0
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            malformed += 1
            continue
        if isinstance(item, dict):
            records.append(item)
        else:
            malformed += 1
    return records, malformed


def aggregate(records, oracle, required_runs=20, batch_id=None, malformed=0) -> dict:
    eligible, excluded = [], {"legacy_schema": 0, "not_cloud": 0, "not_fresh": 0, "other_batch": 0,
                              "duplicate_run_id": 0, "unknown_scenario": 0}
    seen = set()
    for r in records:
        if batch_id and r.get("batch_id") != batch_id:
            excluded["other_batch"] += 1; continue
        if (r.get("schema_version") or 1) < 2:
            excluded["legacy_schema"] += 1; continue
        if r.get("execution_mode") != "celesto_cloud":
            excluded["not_cloud"] += 1; continue
        if r.get("fresh") is not True:
            excluded["not_fresh"] += 1; continue
        if r.get("scenario_id") not in oracle:
            excluded["unknown_scenario"] += 1; continue
        if r.get("run_id") in seen:
            excluded["duplicate_run_id"] += 1; continue
        seen.add(r.get("run_id")); eligible.append(r)

    env_failures = [r for r in eligible if r.get("env_failure") or r.get("interrupted")]
    scored = [r for r in eligible if r not in env_failures]
    tp = fp = fn = tn = 0
    correct = window_ok = window_n = line_ok = line_n = 0
    for r in scored:
        expected = oracle[r["scenario_id"]]["expected_label"]
        verdict = r.get("verdict")
        pos_pred, pos_true = verdict in DATE_BUG_VERDICTS, expected == "date_bug"
        correct += pos_pred if pos_true else verdict == expected
        tp += pos_pred and pos_true; fp += pos_pred and not pos_true
        fn += (not pos_pred) and pos_true; tn += (not pos_pred) and not pos_true
        sc = r.get("score") or {}
        if sc.get("window_ok") is not None:
            window_n += 1; window_ok += bool(sc["window_ok"])
        if sc.get("line_ok") is not None:
            line_n += 1; line_ok += bool(sc["line_ok"])
    walls = [r["wall_clock_s"] for r in eligible if isinstance(r.get("wall_clock_s"), (int, float))]
    reasons = []
    if len(eligible) < required_runs:
        reasons.append(f"only {len(eligible)} eligible fresh cloud runs; {required_runs} required")
    if env_failures:
        reasons.append(f"{len(env_failures)} runs were environment failures or interrupted and are not scored")
    if any(r.get("cleanup_success") is False for r in eligible):
        reasons.append("at least one computer failed cleanup")
    fallback_runs = sum(1 for r in eligible if r.get("plan_fallback"))
    if fallback_runs:
        reasons.append(f"{fallback_runs} runs used fixed fallback dates instead of an LLM plan")
    complete = len(eligible) >= required_runs and not env_failures and not fallback_runs
    return {
        "schema": SCHEMA,
        "status": "complete" if complete else "incomplete",
        "incomplete_reasons": reasons,
        "batch_id": batch_id,
        "required_runs": required_runs,
        "eligible_runs": len(eligible),
        "scored_runs": len(scored),
        "environment_failures": len(env_failures),
        "llm_fallback_runs": fallback_runs,
        "excluded": excluded,
        "malformed_ledger_lines": malformed,
        "accuracy_over_scored": (correct / len(scored)) if scored else None,
        "accuracy_wilson95": wilson(correct, len(scored)),
        "confusion_date_bug_positive": {"tp": tp, "fp": fp, "fn": fn, "tn": tn},
        "window_accuracy": (window_ok / window_n) if window_n else None,
        "line_accuracy": (line_ok / line_n) if line_n else None,
        "failure_classes": _count(eligible, "failure_class"),
        "median_wall_clock_s": _pct(walls, 0.5),
        "p90_wall_clock_s": _pct(walls, 0.9),
        "cost_usd_estimate": round(sum(r.get("cost_usd", 0.0) for r in eligible), 6),
        "cost_basis": "runner hourly estimate, not provider billing",
    }


def _count(rows, key):
    out = {}
    for r in rows:
        out[str(r.get(key))] = out.get(str(r.get(key)), 0) + 1
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--ledger", type=Path, default=ROOT / "reports" / "benchmark_results.jsonl")
    ap.add_argument("--batch-id")
    ap.add_argument("--required-runs", type=int, default=20)
    ap.add_argument("--output", type=Path, required=True, help="new JSON file inside reports/")
    a = ap.parse_args(argv)
    out = (a.output if a.output.is_absolute() else ROOT / a.output).resolve()
    try:
        out.relative_to((ROOT / "reports").resolve())
    except ValueError:
        print("--output must be inside reports/", file=sys.stderr); return 2
    if out.exists():
        print("--output already exists; choose a new path", file=sys.stderr); return 2
    sys.path.insert(0, str(ROOT))
    from agent.run_local_fixtures import load_oracle
    try:
        oracle = load_oracle(ROOT / "oracle" / "labels.jsonl")
        records, malformed = load_ledger(a.ledger)
    except (OSError, ValueError) as exc:
        print(f"cannot evaluate: {type(exc).__name__}", file=sys.stderr); return 2
    report = aggregate(records, oracle, a.required_runs, a.batch_id, malformed)
    with out.open("x", encoding="utf-8") as fh:
        fh.write(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))
    return 0 if report["status"] == "complete" else 1


if __name__ == "__main__":
    raise SystemExit(main())
