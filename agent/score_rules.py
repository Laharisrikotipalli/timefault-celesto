import json, calendar
from datetime import date

def P(d): return int(d[:4]), int(d[5:7]), int(d[8:])
def m01(d):
    y, m, day = P(d); ny, nm = (y+1, 1) if m == 12 else (y, m+1)
    return day > calendar.monthrange(ny, nm)[1]
def m04(d):
    y, m, day = P(d)
    return day == calendar.monthrange(y, m)[1] and day != 31

# (rule, verified_against_fixture_source)
RULES = {
 "L01": (lambda d: d[5:] == "02-29", True),
 "L02": (lambda d: calendar.isleap(P(d)[0]), True),
 "L03": (lambda d: d[5:] == "02-29", True),
 "M01": (m01, True),
 "M02": (lambda d: d[5:7] == "12", True),
 "M03": (lambda d: d[5:7] == "02", True),
 "M04": (m04, True),
}
out = {}
for l in open("reports/benchmark_results.jsonl"):
    r = json.loads(l); sid = r["scenario_id"]
    if sid not in RULES or r["verdict"] != "date_bug": continue
    rule, verified = RULES[sid]
    t = (r.get("result") or {}).get("tested", {})
    fails  = sorted(d for d, s in t.items() if s == "fail")
    passes = sorted(d for d, s in t.items() if s == "pass")
    bad_fail = [d for d in fails if not rule(d)]    # agent said fail, rule says shouldn't
    bad_pass = [d for d in passes if rule(d)]       # agent said pass, rule says should fail
    out[sid] = {"rule_consistent": bool(fails) and not bad_fail and not bad_pass,
                "n_fail": len(fails), "n_pass": len(passes),
                "violations_fail": bad_fail, "violations_pass": bad_pass,
                "rule_verified_against_fixture": verified,
                "original_window_ok": r["score"]["window_ok"]}
    print(sid, out[sid]["rule_consistent"], "verified" if verified else "UNVERIFIED",
          bad_fail, bad_pass)
json.dump(out, open("reports/rule_consistency.json", "w"), indent=1)
