import argparse, base64, json, math, secrets, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_one as R
import investigate as I

ROOT = R.ROOT
INSTALL = "apt-get update -qq && apt-get install -y -qq faketime python3 >/dev/null 2>&1; mkdir -p /work"
PROBE = (
    'faketime "2028-02-29 12:00:00" python3 -c '
    '"from datetime import date; print(date.today().isoformat())"'
)
RATE = 0.015 / 3600  # Micro $/s (estimate, state this in the README)

def median(v):
    v = sorted(v); n = len(v)
    return v[n // 2] if n % 2 else (v[n // 2 - 1] + v[n // 2]) / 2

def run_scenario(sid, o, reuse_id=None):
    name = "sbx-" + secrets.token_hex(4)
    rec = {"scenario_id": sid, "sandbox_name": name, "fresh": True, "success": False,
           "boot_to_ready_s": 0.0, "env_failure": False, "verdict": None}
    t0 = time.time(); created = False
    try:
        if reuse_id:
            cid = reuse_id
            rec["fresh"] = False
        else:
            c = R.cli(["create", "--boot-timeout", "90"])
            cid = (c.get("data") or {}).get("computer_id")
            if not c.get("ok") or not cid:
                rec.update(env_failure=True, note="create failed")
                return rec
            created = True

        R.MAP[name] = cid
        rec["computer_id"] = cid

        if reuse_id:
            # Reused guests should already have their runtime installed.
            # Verify it instead of running apt-get on every scenario.
            install = I.gexec(
                name,
                "command -v python3 >/dev/null && command -v faketime >/dev/null && mkdir -p /work",
                label="verify reused sandbox runtime",
            )
        else:
            install = I.gexec(name, INSTALL)

        if install.get("env_error") or install.get("exit_code") != 0:
            rec.update(env_failure=True, note="runtime setup or verification failed")
            return rec
        p = I.gexec(name, PROBE)
        observed = (p.get("stdout") or "").strip()
        if p.get("env_error") or p.get("exit_code") != 0 or observed != "2028-02-29":
            rec.update(
                env_failure=True,
                note=f"clock probe failed; observed={observed!r}",
            )
            return rec
        rec["boot_to_ready_s"] = round(time.time() - t0, 2)
        src = I.strip_hints((ROOT / "fixtures" / sid / "app.py").read_text())
        b64 = base64.b64encode(src.encode()).decode()
        I.gexec(name, f"echo {b64} | base64 -d > /work/app.py", label="upload app.py")
        res = I.investigate(name, src)
        rec["verdict"] = res["verdict"]; rec["env_failure"] = res["verdict"] == "env_failure"
        rec["score"] = I.score(o, res)
        rec["success"] = (not rec["env_failure"]) and rec["score"]["label_ok"]
        rec["result"] = res
        if res["verdict"] in {"date_bug", "date_bug_candidate"}:
            rec["replay"] = f'faketime "{res["first_failure"]} 12:00:00" python3 fixtures/{sid}/app.py'
        (ROOT / "reports" / "evidence").mkdir(parents=True, exist_ok=True)
        (ROOT / "reports" / "evidence" / f"{sid}.json").write_text(json.dumps(rec, indent=2))
        return rec
    except Exception as e:
        rec.update(env_failure=True, note=repr(e)[:200]); return rec
    finally:                      # success, failure and Ctrl-C all land here
        if created:
            R.cli(["delete", R.MAP[name]], input_text="y\n")
        rec["wall_clock_s"] = round(time.time() - t0, 2)
        rec["cost_usd"] = round(rec["wall_clock_s"] * RATE, 6)

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--only", default=""); ap.add_argument("--reuse", default="")
    a = ap.parse_args()
    oracle = {}
    for l in (ROOT / "oracle" / "labels.jsonl").read_text().splitlines():
        if l.strip(): oracle[json.loads(l)["scenario_id"]] = json.loads(l)
    ids = [s for s in oracle if not a.only or s in a.only.split(",")]
    runs = []
    out = ROOT / "reports" / "benchmark_results.jsonl"
    out.write_text("")
    try:
        for sid in ids:
            rec = run_scenario(sid, oracle[sid], reuse_id=a.reuse or None); runs.append(rec)
            with out.open("a") as f: f.write(json.dumps(rec) + "\n")
            print(sid, rec["verdict"], "ok" if rec["success"] else "MISS", rec["wall_clock_s"], "s", rec.get("note", ""))
    except KeyboardInterrupt:
        print("interrupted; guest cleanup ran in finally")
    n = len(runs)
    if not n: return
    walls = [r["wall_clock_s"] for r in runs]
    summary = {
      "run_count": n,
      "runs": [{k: r[k] for k in ("sandbox_name","fresh","success","wall_clock_s","boot_to_ready_s","cost_usd")} for r in runs],
      "success_rate": sum(r["success"] for r in runs) / n,
      "median_wall_clock_s": median(walls),
      "p90_wall_clock_s": sorted(walls)[math.ceil(0.9 * n) - 1],
      "median_boot_to_ready_s": median([r["boot_to_ready_s"] for r in runs]),
      "total_cost_usd": sum(r["cost_usd"] for r in runs),
      "postmortem_path": "reports/postmortem.md"}
    dest = "reliability.json" if n >= 20 else "reliability_partial.json"
    (ROOT / "reports" / dest).write_text(json.dumps(summary, indent=2))
    scored = [r for r in runs if not r["env_failure"]]
    tp = sum(1 for r in scored if r["verdict"] in {"date_bug", "date_bug_candidate"} and oracle[r["scenario_id"]]["expected_label"] == "date_bug")
    fp = sum(1 for r in scored if r["verdict"] in {"date_bug", "date_bug_candidate"} and oracle[r["scenario_id"]]["expected_label"] != "date_bug")
    fn = sum(1 for r in scored if r["verdict"] not in {"date_bug", "date_bug_candidate"} and oracle[r["scenario_id"]]["expected_label"] == "date_bug")
    tn = len(scored) - tp - fp - fn
    print(f"\nwrote reports/{dest}  success_rate={summary['success_rate']:.2f}")
    print(f"confusion (date_bug positive): TP={tp} FP={fp} FN={fn} TN={tn}  env_failures={n-len(scored)}")
    chk = R.cli(["list"])
    left = (chk.get("data") or {}).get("computers")
    print("guests left on account:", left)

if __name__ == "__main__":
    main()
