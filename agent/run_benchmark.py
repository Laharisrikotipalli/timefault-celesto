"""Cloud benchmark runner. Allocates Celesto computers only with --confirm-cloud.

Exit codes: 0 all runs completed cleanly and matched the oracle; 1 completed but
at least one product/scoring miss; 2 prerequisite or argument error (nothing
allocated); 3 environment/setup/transport/ambiguous/time-control failure or a
cleanup failure; 130 interrupted.
"""

import argparse, base64, json, math, re, secrets, shutil, sys, threading, time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from agent import policy as P  # noqa: E402
from agent.sanitize import redact  # noqa: E402

DATE_BUG_VERDICTS = frozenset({"date_bug", "date_bug_candidate"})
REPORTS = ROOT / "reports"
EVIDENCE_DIR = REPORTS / "evidence"
SCHEMA_VERSION = 2
EXECUTION_MODE = "celesto_cloud"
MAX_RUNS = 20
USED_SANDBOX_NAMES: set[str] = set()
_NAME_LOCK = threading.Lock()
INSTALL = P.INSTALL
PROBE = P.PROBE
RATE = 0.015 / 3600  # Micro $/s (estimate, state this in the README)
RUN_ID_PATTERN = re.compile(r"^run-[0-9a-f]{32}$")
EXIT_OK, EXIT_MISS, EXIT_PREREQ, EXIT_ENV, EXIT_INTERRUPT = 0, 1, 2, 3, 130


def append_jsonl_record(path, record):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")


def write_json_report(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{time.time_ns()}.tmp")
    try:
        temporary.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        if path.exists():
            backup = path.with_name(f"{path.name}.backup-{time.time_ns()}")
            shutil.copy2(path, backup)
        temporary.replace(path)
    finally:
        if temporary.exists():
            temporary.unlink()


def write_new_json(path, payload):
    """Create ``path`` exclusively; refuse to replace an existing evidence file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, indent=2))


def evidence_path_for(run_id, evidence_dir=None):
    """Return the evidence file path for a run ID, confined to the evidence directory."""
    if not isinstance(run_id, str) or not RUN_ID_PATTERN.fullmatch(run_id):
        raise ValueError("run_id must match run-<32 hex characters>")
    base = (evidence_dir or EVIDENCE_DIR).resolve()
    resolved = (base / f"{run_id}.json").resolve()
    resolved.relative_to(base)  # raises ValueError if it escapes
    return resolved


def median(v):
    v = sorted(v); n = len(v)
    return v[n // 2] if n % 2 else (v[n // 2 - 1] + v[n // 2]) / 2


def unique_sandbox_name() -> str:
    with _NAME_LOCK:
        name = "sbx-" + secrets.token_hex(8)
        while name in USED_SANDBOX_NAMES:
            name = "sbx-" + secrets.token_hex(8)
        USED_SANDBOX_NAMES.add(name)
        return name


def select_scenarios(scenario_ids: list[str], only: str, repeat: int) -> list[str]:
    if repeat < 1:
        raise ValueError("--repeat must be at least 1")
    requested = [item for item in only.split(",") if item]
    if len(requested) != len(set(requested)):
        raise ValueError("--only must not contain duplicate scenario IDs")
    unknown = set(requested) - set(scenario_ids)
    if unknown:
        raise ValueError("unknown scenario IDs: " + ", ".join(sorted(unknown)))
    selected = [sid for sid in scenario_ids if not requested or sid in requested]
    total_runs = len(selected) * repeat
    if total_runs > MAX_RUNS:
        raise ValueError(f"requested {total_runs} runs; maximum bounded run count is {MAX_RUNS}")
    return [sid for sid in selected for _ in range(repeat)]


def resolve_summary_path(output: Path | str) -> Path:
    candidate = Path(output)
    resolved = (candidate if candidate.is_absolute() else ROOT / candidate).resolve()
    try:
        resolved.relative_to(REPORTS.resolve())
    except ValueError as exc:
        raise ValueError("--summary must remain inside the reports directory") from exc
    if resolved.exists():
        raise ValueError("--summary already exists; choose a new report path")
    return resolved


def default_summary_path(batch_id: str) -> Path:
    """A new, never-existing path so a default run cannot replace an earlier report."""
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return resolve_summary_path(REPORTS / f"benchmark_summary_{stamp}_{batch_id}.json")


def replay_command(failure_date: str) -> str:
    return P.replay_command(failure_date)


def _failure_class(rec):
    """Separate setup, transport, ambiguous, time-control, and product outcomes."""
    if rec.get("interrupted"):
        return "interrupted"
    if rec.get("env_failure"):
        return rec.get("failure_class") or "transport"
    return "none" if rec.get("success") else "product_miss"


def _classify_guest_failure(result, default="transport"):
    if result.get("blocked"):
        return "internal"
    if result.get("ambiguous"):
        return "ambiguous"
    if result.get("env_error"):
        return "setup" if result.get("category") == "setup" else default
    return "setup"  # command ran but exited nonzero (e.g. package install failed)


def check_cloud_prerequisites(allow_llm_fallback=False):
    """Return a list of problems; empty means the runner may allocate computers."""
    import shutil
    from agent import run_one as R
    from agent import investigate as I
    problems = []
    transport = R.os.environ.get(R.TRANSPORT_ENV, "cli")
    if transport == "sdk":
        try:
            R._load_sdk()
        except RuntimeError as exc:
            problems.append(redact(exc, max_length=300))
    elif shutil.which("celesto") is None:
        problems.append("the `celesto` CLI is not on PATH (pip install -r requirements-cloud.txt)")
    env = I.load_env()
    if not allow_llm_fallback and not ((env.get("LLM_API_KEY") or env.get("OPENAI_API_KEY"))
                                       and env.get("LLM_MODEL")):
        problems.append("LLM_API_KEY (or OPENAI_API_KEY) and LLM_MODEL must be configured "
                        "(or pass --allow-llm-fallback to use fixed default dates)")
    for sid in ("C02",):
        if not (ROOT / "fixtures" / sid / "app.py").is_file():
            problems.append(f"missing fixture {sid}")
    return problems


def run_scenario(sid, o, batch_id=None, reuse_id=None):
    name = unique_sandbox_name()
    rec = {"schema_version": SCHEMA_VERSION, "execution_mode": EXECUTION_MODE,
           "batch_id": batch_id, "run_id": "run-" + secrets.token_hex(16),
           "scenario_id": sid, "sandbox_name": name, "fresh": False, "success": False,
           "boot_to_ready_s": 0.0, "env_failure": False, "verdict": None,
           "cleanup_success": None, "failure_class": None}
    t0 = time.time(); created = False
    try:
        from agent import run_one as R
        from agent import investigate as I

        if sid not in P.load_allowed_scenarios():
            rec.update(env_failure=True, failure_class="internal",
                       note="scenario is not on the allowlist")
            return rec
        if reuse_id:
            # A reused computer is never created or deleted by this run, and its
            # results are not "fresh" evidence.
            cid = reuse_id
            R.MAP[name] = cid; rec["computer_id"] = cid; rec["reused"] = True
            setup = I.gexec(name, P.VERIFY_RUNTIME, label="verify reused computer runtime")
        else:
            c = R.cli(["create", "--boot-timeout", "90"])
            cid = (c.get("data") or {}).get("computer_id")
            if not c.get("ok") or not cid:
                error = c.get("error") or {}
                rec.update(
                    env_failure=True,
                    failure_class="ambiguous" if error.get("ambiguous") else (
                        "setup" if error.get("category") == "setup" else "transport"),
                    note="create failed",
                    adapter_error={k: v for k, v in error.items()},
                )
                return rec
            rec["fresh"] = True
            R.MAP[name] = cid; created = True; rec["computer_id"] = cid
            setup = I.gexec(name, INSTALL, label="install date-test prerequisites")
        if setup.get("env_error") or setup.get("blocked") or setup.get("exit_code") != 0:
            rec.update(
                env_failure=True,
                failure_class=_classify_guest_failure(setup),
                note="guest prerequisite setup failed",
                setup_error=redact(setup.get("err") or setup.get("stderr"), max_length=500),
            )
            return rec
        ok, detail = I.verify_time_control(name)
        if not ok:
            rec.update(env_failure=True, failure_class="time_control",
                       note="boot probe failed: " + detail)
            return rec
        rec["boot_to_ready_s"] = round(time.time() - t0, 2)
        src = I.strip_hints((ROOT / "fixtures" / sid / "app.py").read_text(encoding="utf-8"))
        b64 = base64.b64encode(src.encode()).decode()
        uploaded = I.gexec(name, P.upload_command(b64), label="upload app.py")
        if uploaded.get("env_error") or uploaded.get("blocked") or uploaded.get("exit_code") != 0:
            rec.update(
                env_failure=True,
                failure_class=_classify_guest_failure(uploaded),
                note="fixture upload failed",
                upload_error=redact(uploaded.get("err") or uploaded.get("stderr"), max_length=500),
            )
            return rec
        res = I.investigate(name, src)
        rec["verdict"] = res["verdict"]; rec["env_failure"] = res["verdict"] == "env_failure"
        if rec["env_failure"]:
            tested = res.get("tested") or {}
            rec["failure_class"] = ("time_control" if "time_control_error" in tested.values()
                                    else "transport")
        rec["plan_fallback"] = bool((res.get("plan") or {}).get("fallback"))
        rec["score"] = I.score(o, res)
        rec["success"] = (not rec["env_failure"]) and rec["score"]["label_ok"]
        rec["result"] = res
        if res["verdict"] in DATE_BUG_VERDICTS:
            rec["replay"] = replay_command(res["first_failure"])
        return rec
    except KeyboardInterrupt as exc:
        rec.update(interrupted=True, success=False, note="interrupted")
        exc.record = rec
        raise
    except Exception as exc:
        rec.update(env_failure=True, failure_class="internal",
                   note=f"{type(exc).__name__}: execution failed")
        return rec
    finally:                      # success, failure and Ctrl-C all land here
        if reuse_id:
            try:
                R.MAP.pop(name, None)
            except NameError:  # adapter import failed before R was bound
                pass
        if created:
            try:
                cleanup = R.cli(["delete", R.MAP[name]], input_text="y\n")
            except Exception as exc:
                rec["cleanup_success"] = False
                rec["cleanup_error_type"] = type(exc).__name__
            else:
                rec["cleanup_success"] = bool(cleanup.get("ok")) if isinstance(cleanup, dict) else False
                if not rec["cleanup_success"]:
                    rec["cleanup_error_type"] = ((cleanup or {}).get("error") or {}).get("type")
            if rec["cleanup_success"]:
                R.MAP.pop(name, None)
            else:
                rec["leaked_computer_id"] = rec.get("computer_id")
        rec["wall_clock_s"] = round(time.time() - t0, 2)
        rec["cost_usd"] = round(rec["wall_clock_s"] * RATE, 6) if created else 0.0
        rec["cost_basis"] = "hourly estimate" if created else "no computer allocation created"
        rec["failure_class"] = _failure_class(rec) if rec["failure_class"] is None or not rec["env_failure"] else rec["failure_class"]
        try:
            rec["evidence_path"] = f"reports/evidence/{rec['run_id']}.json"
            write_new_json(evidence_path_for(rec["run_id"]), rec)
        except (OSError, ValueError) as exc:
            rec["evidence_path"] = None
            rec["evidence_persistence_error"] = type(exc).__name__
            rec["success"] = False


def _load_oracle():
    oracle = {}
    oracle_path = ROOT / "oracle" / "labels.jsonl"
    for line in oracle_path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            record = json.loads(line)
            oracle[record["scenario_id"]] = record
    return oracle


def build_summary(runs, batch_id):
    n = len(runs)
    walls = [r["wall_clock_s"] for r in runs]
    scored = [r for r in runs if not r["env_failure"] and not r.get("interrupted")]
    classes = {}
    for r in runs:
        classes[r["failure_class"]] = classes.get(r["failure_class"], 0) + 1
    return {
        "schema_version": SCHEMA_VERSION,
        "execution_mode": EXECUTION_MODE,
        "batch_id": batch_id,
        "run_count": n,
        "scored_count": len(scored),
        "env_failure_count": sum(1 for r in runs if r["env_failure"]),
        "cleanup_failure_count": sum(1 for r in runs if r.get("cleanup_success") is False),
        "llm_fallback_run_count": sum(1 for r in runs if r.get("plan_fallback")),
        "failure_classes": classes,
        "runs": [{k: r.get(k) for k in ("run_id", "scenario_id", "sandbox_name", "fresh", "success",
                                        "failure_class", "wall_clock_s", "boot_to_ready_s", "cost_usd")}
                 for r in runs],
        "success_rate": sum(r["success"] for r in runs) / n,
        "median_wall_clock_s": median(walls),
        "p90_wall_clock_s": sorted(walls)[math.ceil(0.9 * n) - 1],
        "median_boot_to_ready_s": median([r["boot_to_ready_s"] for r in runs]),
        "total_cost_usd": sum(r["cost_usd"] for r in runs),
        "cost_basis": "runner hourly estimate, not provider billing",
        "postmortem_path": "reports/postmortem.md",
    }


def exit_code_for(runs):
    if any(r["env_failure"] or r.get("cleanup_success") is False for r in runs):
        return EXIT_ENV
    if any(not r["success"] for r in runs):
        return EXIT_MISS
    return EXIT_OK


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--only", default="")
    ap.add_argument("--repeat", type=int, default=1)
    ap.add_argument("--summary", type=Path)
    ap.add_argument("--reuse", default="",
                    help="existing Celesto computer ID to reuse (never deleted; results are not fresh evidence)")
    ap.add_argument("--confirm-cloud", action="store_true",
                    help="required: acknowledge that this allocates billable Celesto computers")
    ap.add_argument("--allow-llm-fallback", action="store_true",
                    help="permit fixed default dates when no LLM is configured")
    a = ap.parse_args(argv)
    if not a.confirm_cloud:
        print("benchmark not started: pass --confirm-cloud to allow Celesto allocations",
              file=sys.stderr)
        return EXIT_PREREQ
    if not (Path(__file__).resolve().parent / "run_one.py").is_file():
        print("benchmark cannot run: missing Celesto adapter agent/run_one.py", file=sys.stderr)
        return EXIT_PREREQ
    try:
        from agent import run_one as R
    except ModuleNotFoundError as exc:
        print(f"benchmark cannot load Celesto adapter ({type(exc).__name__})", file=sys.stderr)
        return EXIT_PREREQ

    if not (ROOT / "oracle" / "labels.jsonl").is_file():
        print("benchmark cannot run: missing oracle/original fixture data", file=sys.stderr)
        return EXIT_PREREQ
    try:
        oracle = _load_oracle()
    except (json.JSONDecodeError, KeyError):
        print("benchmark cannot run: malformed oracle data", file=sys.stderr)
        return EXIT_PREREQ
    try:
        ids = select_scenarios(list(oracle), a.only, a.repeat)
    except ValueError as exc:
        print(f"benchmark arguments rejected: {exc}", file=sys.stderr)
        return EXIT_PREREQ
    batch_id = "batch-" + secrets.token_hex(8)
    try:
        summary_output = resolve_summary_path(a.summary) if a.summary else default_summary_path(batch_id)
    except ValueError as exc:
        print(f"benchmark report path rejected: {exc}", file=sys.stderr)
        return EXIT_PREREQ
    allowed = P.load_allowed_scenarios()
    missing_fixtures = [sid for sid in ids if sid not in allowed]
    if missing_fixtures:
        print("benchmark cannot run: missing fixture files for " + ", ".join(sorted(set(missing_fixtures))),
              file=sys.stderr)
        return EXIT_PREREQ
    problems = check_cloud_prerequisites(a.allow_llm_fallback)
    if problems:
        for problem in problems:
            print("benchmark prerequisite missing: " + problem, file=sys.stderr)
        print("nothing was allocated and no ledger rows were written", file=sys.stderr)
        return EXIT_PREREQ

    runs = []
    out = REPORTS / "benchmark_results.jsonl"
    interrupted = False
    try:
        for sid in ids:
            rec = run_scenario(sid, oracle[sid], batch_id, reuse_id=a.reuse or None); runs.append(rec)
            append_jsonl_record(out, rec)
            print(sid, rec["verdict"], "ok" if rec["success"] else "MISS", rec["failure_class"],
                  rec["wall_clock_s"], "s", rec.get("note", ""))
            if rec["failure_class"] in ("setup", "internal") and not rec["fresh"]:
                print("stopping: setup failure before any computer was allocated", file=sys.stderr)
                break
    except KeyboardInterrupt as exc:
        interrupted = True
        rec = getattr(exc, "record", None)
        if rec is not None:
            runs.append(rec); append_jsonl_record(out, rec)
        print("interrupted; guest cleanup ran in finally")
    if not runs:
        print("benchmark did not complete any scenarios", file=sys.stderr)
        return EXIT_ENV
    summary = build_summary(runs, batch_id)
    write_json_report(summary_output, summary)
    scored = [r for r in runs if not r["env_failure"] and not r.get("interrupted")]
    tp = sum(1 for r in scored if r["verdict"] in DATE_BUG_VERDICTS and oracle[r["scenario_id"]]["expected_label"] == "date_bug")
    fp = sum(1 for r in scored if r["verdict"] in DATE_BUG_VERDICTS and oracle[r["scenario_id"]]["expected_label"] != "date_bug")
    fn = sum(1 for r in scored if r["verdict"] not in DATE_BUG_VERDICTS and oracle[r["scenario_id"]]["expected_label"] == "date_bug")
    tn = len(scored) - tp - fp - fn
    try:
        shown = summary_output.relative_to(ROOT).as_posix()
    except ValueError:
        shown = str(summary_output)
    print(f"\nwrote {shown}  success_rate={summary['success_rate']:.2f}")
    print(f"confusion (date_bug positive): TP={tp} FP={fp} FN={fn} TN={tn}  "
          f"env_failures={summary['env_failure_count']}")
    chk = R.cli(["list"])
    owned = (chk.get("data") or {}).get("computers")
    print("runner-tracked computers not yet deleted:", len(owned) if isinstance(owned, list) else "unknown",
          "(this lists only handles held by this process, not provider-wide state)")
    if interrupted:
        return EXIT_INTERRUPT
    return exit_code_for(runs)


if __name__ == "__main__":
    raise SystemExit(main())
