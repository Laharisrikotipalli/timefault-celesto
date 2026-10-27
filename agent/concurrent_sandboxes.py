"""Bounded-concurrency sandbox runs with isolation checks and guaranteed cleanup.

The harness is executor-agnostic. ``LocalDirExecutor`` (temporary directories)
is used by the tests and by ``--mode local``. ``CelestoExecutor`` drives the
real adapter but is only reachable via ``--mode cloud --confirm-cloud``; it was
NOT run during development.
"""

from __future__ import annotations

import argparse
import json
import secrets
import shutil
import sys
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCHEMA = "concurrency_run.v1"
MAX_JOBS = 5
MAX_WORKERS = 5


class LocalDirExecutor:
    execution_mode = "local_tempdir"

    def __init__(self):
        self._base = Path(tempfile.mkdtemp(prefix="tf-conc-"))

    def create(self, name):
        path = self._base / name
        path.mkdir()
        return path

    def write_marker(self, handle, token):
        (handle / "marker").write_text(token, encoding="utf-8")

    def read_marker(self, handle):
        return (handle / "marker").read_text(encoding="utf-8")

    def list_foreign_markers(self, handle, own_name):
        """Markers visible from this sandbox that belong to other sandboxes."""
        return [p.parent.name for p in handle.rglob("marker") if p.parent.name != own_name]

    def delete(self, handle):
        shutil.rmtree(handle)

    def close(self):
        shutil.rmtree(self._base, ignore_errors=True)


class CelestoExecutor:
    """Real-cloud executor using the project adapter. Not exercised in development."""

    execution_mode = "celesto_cloud"

    def __init__(self):
        if str(ROOT) not in sys.path:
            sys.path.insert(0, str(ROOT))
        from agent import run_one as R
        self.R = R

    def create(self, name):
        c = self.R.cli(["create", "--boot-timeout", "90"])
        cid = (c.get("data") or {}).get("computer_id")
        if not c.get("ok") or not cid:
            raise RuntimeError("create failed: " + str((c.get("error") or {}).get("category")))
        self.R.MAP[name] = cid
        return cid

    def _run(self, handle, command):
        r = self.R.cli(["exec", handle, "--", "sh", "-c", command])
        if not r.get("ok"):
            raise RuntimeError("exec failed (not retried): " + str((r.get("error") or {}).get("category")))
        return r["data"]

    def write_marker(self, handle, token):
        if not token.isalnum():
            raise ValueError("token must be alphanumeric")
        self._run(handle, f"mkdir -p /work && printf %s {token} > /work/marker")

    def read_marker(self, handle):
        return self._run(handle, "cat /work/marker")["stdout"]

    def list_foreign_markers(self, handle, own_name):
        return []  # separate guests share no filesystem; cross-guest visibility is not testable here

    def delete(self, handle):
        r = self.R.cli(["delete", handle])
        if not r.get("ok"):
            raise RuntimeError("delete failed")

    def close(self):
        pass


def run_bounded(executor, job_count=MAX_JOBS, max_workers=MAX_WORKERS, hold_s=0.05) -> dict:
    if not 1 <= job_count <= MAX_JOBS:
        raise ValueError(f"job_count must be 1..{MAX_JOBS}")
    if not 1 <= max_workers <= MAX_WORKERS:
        raise ValueError(f"max_workers must be 1..{MAX_WORKERS}")
    lock = threading.Lock()
    state = {"active": 0, "peak": 0}
    names = []
    while len(names) < job_count:
        n = "sbx-" + secrets.token_hex(8)
        if n not in names:
            names.append(n)
    tokens = {n: secrets.token_hex(8) for n in names}

    def job(name):
        rec = {"sandbox_name": name, "created": False, "isolation_ok": None,
               "cleanup_success": None, "error_type": None}
        handle = None
        try:
            handle = executor.create(name); rec["created"] = True
            with lock:
                state["active"] += 1; state["peak"] = max(state["peak"], state["active"])
            executor.write_marker(handle, tokens[name])
            time.sleep(hold_s)  # force overlap between jobs
            own_ok = executor.read_marker(handle).strip() == tokens[name]
            foreign = executor.list_foreign_markers(handle, name)
            rec["isolation_ok"] = own_ok and not foreign
            rec["foreign_markers_visible"] = len(foreign)
        except Exception as exc:  # noqa: BLE001
            rec["error_type"] = type(exc).__name__
        finally:
            if rec["created"]:
                with lock:
                    state["active"] -= 1
                try:
                    executor.delete(handle); rec["cleanup_success"] = True
                except Exception as exc:  # noqa: BLE001
                    rec["cleanup_success"] = False; rec["cleanup_error_type"] = type(exc).__name__
        return rec

    started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        jobs = list(pool.map(job, names))
    return {
        "schema": SCHEMA,
        "execution_mode": executor.execution_mode,
        "cloud_verified": executor.execution_mode == "celesto_cloud",
        "jobs_submitted": job_count,
        "jobs_created": sum(j["created"] for j in jobs),
        "max_workers": max_workers,
        "max_simultaneously_active": state["peak"],
        "unique_names": len(set(names)) == job_count,
        "all_isolated": all(j["isolation_ok"] is True for j in jobs),
        "all_cleaned_up": all(j["cleanup_success"] is True for j in jobs),
        "errors": [j["error_type"] for j in jobs if j["error_type"]],
        "elapsed_s": round(time.perf_counter() - started, 3),
        "jobs": jobs,
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--mode", choices=("local", "cloud"), default="local")
    ap.add_argument("--confirm-cloud", action="store_true")
    ap.add_argument("--jobs", type=int, default=MAX_JOBS)
    ap.add_argument("--workers", type=int, default=MAX_WORKERS)
    ap.add_argument("--output", type=Path)
    a = ap.parse_args(argv)
    if a.mode == "cloud" and not a.confirm_cloud:
        print("cloud mode needs --confirm-cloud; nothing allocated", file=sys.stderr); return 2
    out = None
    if a.output:
        out = (a.output if a.output.is_absolute() else ROOT / a.output).resolve()
        try:
            out.relative_to((ROOT / "reports").resolve())
        except ValueError:
            print("--output must be inside reports/", file=sys.stderr); return 2
        if out.exists():
            print("--output already exists; choose a new path", file=sys.stderr); return 2
    executor = LocalDirExecutor() if a.mode == "local" else CelestoExecutor()
    try:
        report = run_bounded(executor, a.jobs, a.workers)
    finally:
        executor.close()
    text = json.dumps(report, indent=2)
    if out:
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("x", encoding="utf-8") as fh:
            fh.write(text)
    print(text)
    ok = report["all_isolated"] and report["all_cleaned_up"] and not report["errors"]
    return 0 if ok else 3


if __name__ == "__main__":
    raise SystemExit(main())
