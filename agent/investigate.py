import base64, json, os, re, sys, time
from datetime import date, timedelta
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_one as R
from verdicts import classify

ROOT = R.ROOT
BASELINE = "2027-06-15"
DEFAULTS = ["2028-01-31", "2028-02-28", "2028-02-29", "2028-03-01",
            "2028-12-31", "2038-01-19", "2100-02-28", "2100-03-01"]
REPS = 3

def load_env():
    env = dict(os.environ)
    p = ROOT / ".env"
    if p.exists():
        for l in p.read_text().splitlines():
            if "=" in l and not l.startswith("#"):
                k, v = l.split("=", 1)
                env.setdefault(k.strip(), v.strip())
    return env

def strip_hints(src):
    return "\n".join(re.sub(r"\s*#\s*BUG.*$", "", l) for l in src.splitlines()) + "\n"

def llm_plan(src):
    """The LLM sees only the (hint-stripped) source, never the oracle."""
    env = load_env()
    numbered = "\n".join(f"{i+1}: {l}" for i, l in enumerate(src.splitlines()))
    prompt = ("You investigate date-triggered bugs. The program below runs with the system "
              "date set to a chosen day (time is always 12:00:00). Reply with ONLY JSON: "
              '{"dates": [up to 10 ISO dates YYYY-MM-DD, years 2000-2200, most likely to expose '
              'date-dependent failures], "suspect_line": <line number of the faulty date logic or null>, '
              '"reason": "<one sentence>"}\n\n' + numbered)
    try:
        from openai import OpenAI
        client = OpenAI(base_url=env["LLM_BASE_URL"], api_key=env["LLM_API_KEY"])
        out = client.chat.completions.create(model=env["LLM_MODEL"], temperature=0,
                                             messages=[{"role": "user", "content": prompt}])
        m = re.search(r"\{.*\}", out.choices[0].message.content, re.S)
        plan = json.loads(m.group(0))
        dates = []
        for d in plan.get("dates", []):
            try:
                date.fromisoformat(d)
                if 2000 <= int(d[:4]) <= 2200 and d not in dates:
                    dates.append(d)
            except Exception:
                pass
        return {"dates": dates[:10], "suspect_line": plan.get("suspect_line"),
                "reason": plan.get("reason", ""), "fallback": False}
    except Exception as e:
        return {"dates": DEFAULTS, "suspect_line": None,
                "reason": f"LLM failed, default dates used: {e!r}"[:200], "fallback": True}

def gexec(name, cmd, label=None):
    shown = label or cmd
    if any(re.search(p, cmd) for p in R.DENY):
        R.audit(name, shown, "block")
        return {"blocked": True, "exit_code": None, "stdout": ""}

    errors = []
    for attempt in (1, 2):
        R.audit(
            name,
            shown + ("" if attempt == 1 else "  # retry"),
            "allow",
        )
        r = R.cli(
            ["exec", R.MAP[name], "--", "sh", "-c", cmd],
            timeout=90,
        )
        data = r.get("data")
        if isinstance(data, dict) and "exit_code" in data:
            return {
                "exit_code": data["exit_code"],
                "stdout": data.get("stdout", ""),
                "stderr": data.get("stderr", ""),
            }

        err = (r.get("error") or {}).get("message") or repr(r)[:500]
        errors.append({"attempt": attempt, "error": err})
        time.sleep(2)

    return {
        "env_error": True,
        "err": errors[-1]["error"],
        "attempt_errors": errors,
        "label": shown,
    }

def test_dates(name, dates):
    status = {}

    for d in dates:
        # Confirm that faketime really changes the date seen by Python.
        probe = (
            f'faketime "{d} 12:00:00" python3 -c '
            '"from datetime import date; print(date.today().isoformat())"'
        )
        check = gexec(name, probe, label=f"verify simulated date {d}")

        if check.get("env_error") or check.get("exit_code") != 0:
            status[d] = "env_error"
            continue

        observed = check.get("stdout", "").strip()
        if observed != d:
            status[d] = "time_control_error"
            continue

        results = []
        for _ in range(REPS):
            run = gexec(
                name,
                f'cd /work && faketime "{d} 12:00:00" python3 app.py',
                label=f"fixture test at {d}",
            )
            if run.get("env_error") or run.get("exit_code") is None:
                results.append(None)
            else:
                results.append(run["exit_code"])

        if any(x is None for x in results):
            status[d] = "env_error"
        elif all(x == 0 for x in results):
            status[d] = "pass"
        elif all(x != 0 for x in results):
            status[d] = "fail"
        else:
            status[d] = "flaky"

    return status

def nb(d):
    x = date.fromisoformat(d)
    return [(x - timedelta(days=1)).isoformat(), (x + timedelta(days=1)).isoformat()]

def investigate(name, src):
    plan = llm_plan(src)

    # Staged initial sample: baseline, leap-day boundaries, and
    # the 2038 timestamp boundary. LLM suggestions add targeted dates.
    # Neighbor checks below still verify dates around observed failures.
    boundary_dates = [
        BASELINE,
        "2028-02-28",
        "2028-02-29",
        "2028-03-01",
        "2038-01-19",
    ]
    dates = list(dict.fromkeys(boundary_dates + plan["dates"]))
    status = test_dates(name, dates)
    res = {"plan": plan, "experiments": len(dates) * REPS, "cited_line": plan["suspect_line"]}
    verdict = classify(status or {})
    if verdict == "env_failure":
        return {
            **res,
            "verdict": "env_failure",
            "why": "date-control or execution environment could not be verified",
            "tested": status or {},
        }
    if verdict == "inconclusive":
        # Random failures in code with no apparent date/time logic
        # should not be reported as date-related bugs.
        date_time_patterns = (
            r"\\bdatetime\\b", r"\\bdate\\.today\\b",
            r"\\btime\\.time\\b", r"\\btime\\.localtime\\b",
            r"\\btime\\.gmtime\\b", r"\\bstrftime\\b",
            r"\\bstrptime\\b", r"\\btimedelta\\b",
        )
        has_date_logic = any(
            re.search(pattern, src)
            for pattern in date_time_patterns
        )
        if any(result == "flaky" for result in status.values()) and not has_date_logic:
            return {
                **res,
                "verdict": "not_date_bug",
                "why": "intermittent failures observed without apparent date/time logic",
                "tested": status,
            }
        return {
            **res,
            "verdict": "inconclusive",
            "why": "observed outcomes do not establish a reliable verdict",
            "tested": status,
        }
    if verdict == "clean":
        return {**res, "verdict": "clean", "tested": status}
    if verdict == "not_date_bug":
        return {**res, "verdict": "inconclusive", "tested": status}

    fails = sorted(d for d, s in status.items() if s == "fail")
    extra = sorted({n for d in (fails[0], fails[-1]) for n in nb(d)} - set(status))
    if extra:
        st2 = test_dates(name, extra)
        res["experiments"] += len(extra) * REPS
        if st2:
            status.update({d: s for d, s in st2.items()})
    # Reclassify after neighboring-date experiments.
    final_verdict = classify(status)
    if final_verdict != "date_bug_candidate":
        return {
            **res,
            "verdict": (
                "env_failure"
                if final_verdict == "env_failure"
                else "inconclusive"
            ),
            "why": "boundary experiments did not confirm reliable date-sensitive behavior",
            "tested": dict(sorted(status.items())),
        }

    fails = sorted(d for d, result in status.items() if result == "fail")
    later_pass = sorted(
        d for d, result in status.items()
        if result == "pass" and d > fails[-1]
    )

    return {
        **res,
        "verdict": "date_bug_candidate",
        "first_failure": fails[0],
        "last_failure": fails[-1],
        "recovery": later_pass[0] if later_pass else None,
        "why": "mixed outcomes observed; independent causal confirmation pending",
        "tested": dict(sorted(status.items())),
    }

def score(o, res):
    verdict = res["verdict"]
    is_date_bug = verdict in {"date_bug", "date_bug_candidate"}
    ok = (
        is_date_bug if o["expected_label"] == "date_bug"
        else verdict == o["expected_label"]
    )
    w = o.get("window")
    window_ok = None
    if o["expected_label"] == "date_bug" and is_date_bug:
        first = res.get("first_failure")
        window_ok = bool(first and w and w[0] <= first <= w[1])
    line_ok = None
    if o.get("bug_line") and res.get("cited_line") is not None:
        try: line_ok = abs(int(res["cited_line"]) - o["bug_line"]) <= 1
        except Exception: line_ok = False
    return {"label_ok": ok, "window_ok": window_ok, "line_ok": line_ok}
