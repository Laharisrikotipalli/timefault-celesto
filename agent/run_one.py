import base64, json, re, secrets, subprocess, sys, time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOG = ROOT / "logs" / "commands.jsonl"
# Safety hook: runs on the host BEFORE the guest sees the command.
DENY = [r"rm\s+-rf\s+/(\s|$)", r"mkfs", r"dd\s+if=.*of=/dev/", r"date\s+-s"]
CANDIDATES = ["2027-06-15", "2028-01-31", "2028-02-28", "2028-02-29",
              "2028-03-01", "2028-12-31", "2029-02-28", "2029-03-01"]
MAP = {}  # sbx-name -> Celesto Cloud computer id

def cli(args, input_text=None, timeout=90):
    i = args.index("--") if "--" in args else len(args)
    prefix = ["celesto", "computer", *args[:i]]
    if "exec" in args[:i]:
        prefix.extend(["--timeout", str(timeout)])
    full = prefix + ["--cloud", "--json", *args[i:]]
    try:
        p = subprocess.run(
            full,
            capture_output=True,
            text=True,
            input=input_text,
            timeout=timeout + 10,
        )
    except subprocess.TimeoutExpired:
        return {
            "ok": False,
            "data": None,
            "error": {"message": f"Local CLI timed out after {timeout + 10}s"},
        }
    try:
        result = json.loads(p.stdout)
        if p.returncode != 0 and not result.get("error"):
            result["error"] = {"message": p.stderr[-500:]}
        return result
    except Exception:
        return {
            "ok": False,
            "data": None,
            "error": {"message": (p.stderr or p.stdout)[-500:]},
        }

def audit(name, cmd, decision):
    LOG.parent.mkdir(exist_ok=True)
    with LOG.open("a") as f:
        f.write(json.dumps({"ts": datetime.now(timezone.utc).isoformat(),
                            "sandbox_name": name, "command": cmd,
                            "decision": decision,
                            "execution_target": "celesto_sandbox"}) + "\n")

def run(name, cmd):
    if any(re.search(p, cmd) for p in DENY):
        audit(name, cmd, "block")
        return {"blocked": True, "exit_code": None, "stdout": ""}
    audit(name, cmd, "allow")
    r = cli(["exec", MAP[name], "--", "sh", "-c", cmd])
    if r.get("data") is None:           # 502 / timeout = environment error
        return {"env_error": True, "exit_code": None, "stdout": "",
                "err": (r.get("error") or {}).get("message")}
    return {"exit_code": r["data"]["exit_code"], "stdout": r["data"]["stdout"]}

def main(scenario):
    name = "sbx-" + secrets.token_hex(4)
    app = (ROOT / "fixtures" / scenario / "app.py").read_bytes()
    t0 = time.time()
    created = False
    try:
        c = cli(["create"])
        if not c.get("ok"):
            print("create failed:", c); return
        cid = (c.get("data") or {}).get("computer_id")
        if not cid:
            print("no computer id in:", c); return
        MAP[name] = cid
        created = True
        print("mapped", name, "->", cid)
        run(name, "apt-get update -qq && apt-get install -y -qq faketime python3 >/dev/null 2>&1; mkdir -p /work")
        b64 = base64.b64encode(app).decode()
        run(name, f"echo {b64} | base64 -d > /work/app.py")
        print(f"{name} boot_to_ready_s={round(time.time() - t0, 2)}")
        results = {}
        for d in CANDIDATES:
            r = run(name, f'cd /work && faketime "{d} 12:00:00" python3 app.py')
            status = "env_error" if r.get("env_error") else ("pass" if r["exit_code"] == 0 else "fail")
            results[d] = status
            print(d, status)
        fails = [d for d, s in results.items() if s == "fail"]
        print("failing dates:", fails or "none")
    finally:                            # success, failure and Ctrl-C all land here
        if created:
            cli(["delete", MAP[name]], input_text="y\n")
            print("deleted", name)

if __name__ == "__main__":
    main(sys.argv[1])
