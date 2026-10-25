import json, os, re, sys
from datetime import date, timedelta
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_one as R

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
    api_key = env.get("LLM_API_KEY") or env.get("OPENAI_API_KEY")
    model = env.get("LLM_MODEL")
    if not api_key or not model:
        return {"dates": DEFAULTS, "suspect_line": None,
                "reason": "LLM credentials or model are not configured; default dates used",
                "fallback": True}
    try:
        from openai import OpenAI
        client_options = {"api_key": api_key}
        if env.get("LLM_BASE_URL"):
            client_options["base_url"] = env["LLM_BASE_URL"]
        client = OpenAI(**client_options)
        out = client.chat.completions.create(model=model, temperature=0,
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
                "reason": f"LLM request failed ({type(e).__name__}); default dates used",
                "fallback": True}

def gexec(name, cmd, label=None):
    shown = label or cmd
    if any(re.search(p, cmd) for p in R.DENY):
        R.audit(name, shown, "block")
        return {"blocked": True, "exit_code": None, "stdout": ""}
    R.audit(name, shown, "allow")
    r = R.cli(["exec", R.MAP[name], "--", "sh", "-c", cmd])
    if r.get("data") is not None:
        return {
            "exit_code": r["data"]["exit_code"],
            "stdout": r["data"]["stdout"],
            "stderr": r["data"].get("stderr", ""),
        }
    error = r.get("error") or {}
    return {
        "env_error": True,
        "err": error.get("message", "Celesto command failed without an error message"),
    }

def test_dates(name, dates):
    for d in dates:
        R.audit(name, f'faketime "{d} 12:00:00" python3 app.py  # x{REPS}', "allow")
    loop = ("cd /work; for d in " + " ".join(dates) + "; do for i in " +
            " ".join(map(str, range(REPS))) +
            '; do faketime "$d 12:00:00" python3 app.py >/dev/null 2>&1; echo "R $d $?"; done; done')
    r = gexec(name, loop, label=f"batch {len(dates)} dates x{REPS}")
    if r.get("env_error"):
        return None
    codes = {}
    for line in r["stdout"].splitlines():
        m = re.match(r"R (\S+) (\d+)", line.strip())
        if m:
            codes.setdefault(m.group(1), []).append(int(m.group(2)))
    status = {}
    for d in dates:
        c = codes.get(d, [])
        if len(c) < REPS: status[d] = "env_error"
        elif all(x == 0 for x in c): status[d] = "pass"
        elif all(x != 0 for x in c): status[d] = "fail"
        else: status[d] = "flaky"
    return status

def nb(d):
    x = date.fromisoformat(d)
    return [(x - timedelta(days=1)).isoformat(), (x + timedelta(days=1)).isoformat()]

def investigate(name, src):
    plan = llm_plan(src)
    dates = [BASELINE] + [d for d in plan["dates"] if d != BASELINE]
    status = test_dates(name, dates)
    res = {"plan": plan, "experiments": len(dates) * REPS, "cited_line": plan["suspect_line"]}
    if status is None or "env_error" in status.values():
        return {**res, "verdict": "env_failure", "tested": status or {}}
    vals = list(status.values())
    if "flaky" in vals:
        return {**res, "verdict": "not_date_bug", "why": "flaky", "tested": status}
    fails = sorted(d for d, s in status.items() if s == "fail")
    if len(fails) == len(dates):
        return {**res, "verdict": "not_date_bug", "why": "fails on every date", "tested": status}
    if not fails:
        return {**res, "verdict": "clean", "tested": status}
    extra = sorted({n for d in (fails[0], fails[-1]) for n in nb(d)} - set(status))
    if extra:
        st2 = test_dates(name, extra)
        res["experiments"] += len(extra) * REPS
        if st2:
            status.update({d: s for d, s in st2.items() if s in ("pass", "fail")})
    fails = sorted(d for d, s in status.items() if s == "fail")
    later_pass = sorted(d for d, s in status.items() if s == "pass" and d > fails[-1])
    return {**res, "verdict": "date_bug", "first_failure": fails[0], "last_failure": fails[-1],
            "recovery": later_pass[0] if later_pass else None, "tested": dict(sorted(status.items()))}

def score(o, res):
    ok = res["verdict"] == o["expected_label"]
    w = o.get("window")
    window_ok = None
    if o["expected_label"] == "date_bug" and res["verdict"] == "date_bug":
        window_ok = w[0] <= res["first_failure"] <= w[1]
    line_ok = None
    if o.get("bug_line") and res.get("cited_line") is not None:
        try: line_ok = abs(int(res["cited_line"]) - o["bug_line"]) <= 1
        except Exception: line_ok = False
    return {"label_ok": ok, "window_ok": window_ok, "line_ok": line_ok}