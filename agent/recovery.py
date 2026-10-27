"""Step-7 recovery comparison: resume vs rollback vs fresh start.

LOCAL SIMULATION ONLY. Steps are deterministic file operations in a temporary
directory; no Celesto computer is used. Results carry
``execution_mode: local_simulated_steps`` and must not be reported as cloud
recovery measurements. A cloud executor is intentionally not implemented here.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCHEMA = "recovery_comparison.v1"
EXECUTION_MODE = "local_simulated_steps"
TOTAL_STEPS = 10
FAIL_STEP = 7
EXTERNAL_EFFECT_STEPS = (4, 8)  # non-idempotent steps (e.g. "publish"), tracked outside the workspace
STRATEGIES = ("resume", "rollback", "fresh")


class InjectedFailure(RuntimeError):
    pass


def _digest(workspace: Path) -> str:
    h = hashlib.sha256()
    for path in sorted(workspace.glob("step_*.txt")):
        h.update(path.name.encode()); h.update(path.read_bytes())
    return h.hexdigest()


def _run_step(n, workspace, external, counters, fail_at, failed_flag):
    counters["attempts"] += 1
    if n == fail_at and not failed_flag["done"]:
        failed_flag["done"] = True
        raise InjectedFailure(f"injected failure at step {n}")
    previous = _digest(workspace)
    (workspace / f"step_{n:02d}.txt").write_text(f"step={n};prev={previous}\n", encoding="utf-8")
    counters["completions"] += 1
    if n in EXTERNAL_EFFECT_STEPS:
        external[n] = external.get(n, 0) + 1


def _execute(first, last, workspace, external, counters, fail_at, flag, checkpoints, every):
    for n in range(first, last + 1):
        _run_step(n, workspace, external, counters, fail_at, flag)
        if n % every == 0:
            snap = workspace.parent / f"ckpt_{n:02d}"
            if snap.exists():
                shutil.rmtree(snap)
            shutil.copytree(workspace, snap)
            checkpoints.append(n)


def baseline_digest(every: int = 5) -> str:
    with tempfile.TemporaryDirectory() as tmp:
        ws = Path(tmp) / "ws"; ws.mkdir()
        _execute(1, TOTAL_STEPS, ws, {}, {"attempts": 0, "completions": 0}, None,
                 {"done": False}, [], every)
        return _digest(ws)


def run_strategy(strategy: str, checkpoint_every: int = 5) -> dict:
    if strategy not in STRATEGIES:
        raise ValueError(f"unknown strategy: {strategy}")
    if not 1 <= checkpoint_every <= TOTAL_STEPS:
        raise ValueError("checkpoint_every must be between 1 and 10")
    counters = {"attempts": 0, "completions": 0}
    external: dict[int, int] = {}
    flag = {"done": False}
    checkpoints: list[int] = []
    started = time.perf_counter()
    with tempfile.TemporaryDirectory() as tmp:
        ws = Path(tmp) / "ws"; ws.mkdir()
        failure_seen = False
        try:
            _execute(1, TOTAL_STEPS, ws, external, counters, FAIL_STEP, flag, checkpoints, checkpoint_every)
        except InjectedFailure:
            failure_seen = True
            if strategy == "resume":
                _execute(FAIL_STEP, TOTAL_STEPS, ws, external, counters, FAIL_STEP, flag, checkpoints, checkpoint_every)
            elif strategy == "rollback":
                last = max([c for c in checkpoints if c < FAIL_STEP], default=0)
                shutil.rmtree(ws); ws.mkdir()
                if last:
                    shutil.rmtree(ws)
                    shutil.copytree(ws.parent / f"ckpt_{last:02d}", ws)
                _execute(last + 1, TOTAL_STEPS, ws, external, counters, FAIL_STEP, flag, checkpoints, checkpoint_every)
            else:  # fresh
                shutil.rmtree(ws); ws.mkdir()
                _execute(1, TOTAL_STEPS, ws, external, counters, FAIL_STEP, flag, checkpoints, checkpoint_every)
        final = _digest(ws)
        complete = len(list(ws.glob("step_*.txt"))) == TOTAL_STEPS
    elapsed = time.perf_counter() - started
    return {
        "strategy": strategy,
        "failure_injected_at_step": FAIL_STEP,
        "failure_observed": failure_seen,
        "completed": complete,
        "step_attempts": counters["attempts"],
        "step_completions": counters["completions"],
        "repeated_completions": counters["completions"] - TOTAL_STEPS,
        "duplicate_external_effects": sum(max(0, c - 1) for c in external.values()),
        "final_digest": final,
        "matches_failure_free_baseline": final == baseline_digest(checkpoint_every),
        "elapsed_s": round(elapsed, 6),
    }


def compare(checkpoint_every: int = 5) -> dict:
    return {
        "schema": SCHEMA,
        "execution_mode": EXECUTION_MODE,
        "cloud_verified": False,
        "total_steps": TOTAL_STEPS,
        "checkpoint_every": checkpoint_every,
        "results": [run_strategy(s, checkpoint_every) for s in STRATEGIES],
        "limitations": [
            "Steps are local deterministic file operations, not Celesto guest work.",
            "Elapsed time is not representative of cloud recovery cost.",
            "Celesto 0.1.6 CloudComputer exposes stop/resume but no filesystem snapshot API; "
            "cloud rollback would have to be re-execution from a copied checkpoint.",
        ],
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--mode", choices=("local", "cloud"), default="local")
    ap.add_argument("--checkpoint-every", type=int, default=5)
    ap.add_argument("--output", type=Path, help="new JSON file inside reports/")
    a = ap.parse_args(argv)
    if a.mode == "cloud":
        print("cloud recovery mode is not implemented; no computers were allocated", file=sys.stderr)
        return 2
    report = compare(a.checkpoint_every)
    text = json.dumps(report, indent=2)
    if a.output:
        out = (a.output if a.output.is_absolute() else ROOT / a.output).resolve()
        try:
            out.relative_to((ROOT / "reports").resolve())
        except ValueError:
            print("--output must be inside reports/", file=sys.stderr); return 2
        if out.exists():
            print("--output already exists; choose a new path", file=sys.stderr); return 2
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("x", encoding="utf-8") as fh:
            fh.write(text)
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
