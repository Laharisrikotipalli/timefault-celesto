import argparse, base64, json, math, secrets, shutil, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MAX_RUNS = 20
USED_SANDBOX_NAMES: set[str] = set()
INSTALL = (
    "set -eu; apt-get update -qq; "
    "apt-get install -y -qq faketime python3 >/dev/null; "
    "mkdir -p /work; command -v faketime; command -v python3"
)
PROBE = 'faketime "2028-02-29 12:00:00" python3 -c "print(1)"'
RATE = 0.015 / 3600  # Micro $/s (estimate, state this in the README)


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


def median(v):
    v = sorted(v); n = len(v)
    return v[n // 2] if n % 2 else (v[n // 2 - 1] + v[n // 2]) / 2


def unique_sandbox_name() -> str:
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
        resolved.relative_to((ROOT / "reports").resolve())
    except ValueError as exc:
        raise ValueError("--summary must remain inside the reports directory") from exc
    if resolved.exists():
        raise ValueError("--summary already exists; choose a new report path")
    return resolved


def replay_command(failure_date: str) -> str:
    return f'faketime "{failure_date} 12:00:00" python3 /work/app.py'


def run_scenario(sid, o):
    name = unique_sandbox_name()
    rec = {"run_id": "run-" + secrets.token_hex(16), "scenario_id": sid,
           "sandbox_name": name, "fresh": False, "success": False,
           "boot_to_ready_s": 0.0, "env_failure": False, "verdict": None,
           "cleanup_success": None}
    t0 = time.time(); created = False
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import run_one as R
        import investigate as I

        c = R.cli(["create", "--boot-timeout", "90"])
        cid = (c.get("data") or {}).get("computer_id")
        if not c.get("ok") or not cid:
            rec.update(
                env_failure=True,
                note="create failed",
                adapter_error=c.get("error"),
            )
            return rec
        rec["fresh"] = True
        R.MAP[name] = cid; created = True; rec["computer_id"] = cid
        setup = I.gexec(name, INSTALL, label="install date-test prerequisites")
        if setup.get("env_error") or setup.get("exit_code") != 0:
            rec.update(
                env_failure=True,
                note="guest prerequisite setup failed",
                setup_error=setup.get("err") or setup.get("stderr"),
            )
            return rec
        p = I.gexec(name, PROBE)
        if p.get("env_error") or p.get("exit_code") != 0:
            rec.update(env_failure=True, note="boot probe failed"); return rec
        rec["boot_to_ready_s"] = round(time.time() - t0, 2)
        src = I.strip_hints((ROOT / "fixtures" / sid / "app.py").read_text())
        b64 = base64.b64encode(src.encode()).decode()
        uploaded = I.gexec(name, f"echo {b64} | base64 -d > /work/app.py", label="upload app.py")
        if uploaded.get("env_error") or uploaded.get("exit_code") != 0:
            rec.update(
                env_failure=True,
                note="fixture upload failed",
                upload_error=uploaded.get("err") or uploaded.get("stderr"),
            )
            return rec
        res = I.investigate(name, src)
        rec["verdict"] = res["verdict"]; rec["env_failure"] = res["verdict"] == "env_failure"
        rec["score"] = I.score(o, res)
        rec["success"] = (not rec["env_failure"]) and rec["score"]["label_ok"]
        rec["result"] = res
        if res["verdict"] == "date_bug":
            rec["replay"] = replay_command(res["first_failure"])
        return rec
    except Exception as exc:
        rec.update(env_failure=True, note=f"{type(exc).__name__}: execution failed"); return rec
    finally:                      # success, failure and Ctrl-C all land here
        if created:
            try:
                cleanup = R.cli(["delete", R.MAP[name]], input_text="y\n")
            except Exception as exc:
                rec["cleanup_success"] = False
                rec["cleanup_error_type"] = type(exc).__name__
            else:
                rec["cleanup_success"] = bool(cleanup.get("ok")) if isinstance(cleanup, dict) else False
        rec["wall_clock_s"] = round(time.time() - t0, 2)
        rec["cost_usd"] = round(rec["wall_clock_s"] * RATE, 6) if created else 0.0
        rec["cost_basis"] = "hourly estimate" if created else "no computer allocation created"
        rec["evidence_path"] = f"reports/evidence/{rec['run_id']}.json"
        try:
            write_json_report(ROOT / rec["evidence_path"], rec)
        except OSError as exc:
            rec["evidence_path"] = None
            rec["evidence_persistence_error"] = type(exc).__name__
            rec["success"] = False

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="")
    ap.add_argument("--repeat", type=int, default=1)
    ap.add_argument("--summary", type=Path)
    a = ap.parse_args()
    adapter_dir = Path(__file__).resolve().parent
    if not (adapter_dir / "run_one.py").is_file():
        print("benchmark cannot run: missing Celesto adapter agent/run_one.py", file=sys.stderr)
        return 2
    sys.path.insert(0, str(adapter_dir))
    try:
        import run_one as R
    except ModuleNotFoundError as exc:
        print(f"benchmark cannot load Celesto adapter ({type(exc).__name__})", file=sys.stderr)
        return 2

    oracle = {}
    oracle_path = ROOT / "oracle" / "labels.jsonl"
    if not oracle_path.is_file():
        print("benchmark cannot run: missing oracle/original fixture data", file=sys.stderr)
        return 2
    try:
        for line in oracle_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                record = json.loads(line)
                oracle[record["scenario_id"]] = record
    except (json.JSONDecodeError, KeyError):
        print("benchmark cannot run: malformed oracle data", file=sys.stderr)
        return 2
    try:
        ids = select_scenarios(list(oracle), a.only, a.repeat)
    except ValueError as exc:
        print(f"benchmark arguments rejected: {exc}", file=sys.stderr)
        return 2
    try:
        summary_output = resolve_summary_path(a.summary) if a.summary else None
    except ValueError as exc:
        print(f"benchmark report path rejected: {exc}", file=sys.stderr)
        return 2
    missing_fixtures = [sid for sid in ids if not (ROOT / "fixtures" / sid / "app.py").is_file()]
    if missing_fixtures:
        print("benchmark cannot run: missing fixture files for " + ", ".join(missing_fixtures),
              file=sys.stderr)
        return 2
    runs = []
    out = ROOT / "reports" / "benchmark_results.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)
    try:
        for sid in ids:
            rec = run_scenario(sid, oracle[sid]); runs.append(rec)
            append_jsonl_record(out, rec)
            print(sid, rec["verdict"], "ok" if rec["success"] else "MISS", rec["wall_clock_s"], "s", rec.get("note", ""))
    except KeyboardInterrupt:
        print("interrupted; guest cleanup ran in finally")
    n = len(runs)
    if not n:
        print("benchmark did not complete any scenarios", file=sys.stderr)
        return 1
    walls = [r["wall_clock_s"] for r in runs]
    summary = {
      "run_count": n,
      "runs": [{k: r[k] for k in ("run_id","sandbox_name","fresh","success","wall_clock_s","boot_to_ready_s","cost_usd")} for r in runs],
      "success_rate": sum(r["success"] for r in runs) / n,
      "median_wall_clock_s": median(walls),
      "p90_wall_clock_s": sorted(walls)[math.ceil(0.9 * n) - 1],
      "median_boot_to_ready_s": median([r["boot_to_ready_s"] for r in runs]),
      "total_cost_usd": sum(r["cost_usd"] for r in runs),
      "postmortem_path": "reports/postmortem.md"}
    dest = "reliability.json" if n >= 20 else "reliability_partial.json"
    summary_path = summary_output or ROOT / "reports" / dest
    write_json_report(summary_path, summary)
    scored = [r for r in runs if not r["env_failure"]]
    tp = sum(1 for r in scored if r["verdict"] == "date_bug" and oracle[r["scenario_id"]]["expected_label"] == "date_bug")
    fp = sum(1 for r in scored if r["verdict"] == "date_bug" and oracle[r["scenario_id"]]["expected_label"] != "date_bug")
    fn = sum(1 for r in scored if r["verdict"] != "date_bug" and oracle[r["scenario_id"]]["expected_label"] == "date_bug")
    tn = len(scored) - tp - fp - fn
    print(f"\nwrote {summary_path.relative_to(ROOT).as_posix()}  success_rate={summary['success_rate']:.2f}")
    print(f"confusion (date_bug positive): TP={tp} FP={fp} FN={fn} TN={tn}  env_failures={n-len(scored)}")
    chk = R.cli(["list"])
    owned = (chk.get("data") or {}).get("computers")
    left = len(owned) if isinstance(owned, list) else "unknown"
    print("runner-owned computers left:", left)

if __name__ == "__main__":
    raise SystemExit(main())