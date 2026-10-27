"""Test helpers. LocalGuest emulates the Celesto adapter by running guest commands locally.

It is a LOCAL EMULATION used by tests only: commands run in a temp directory with
the local libfaketime, never in a Celesto computer.
"""

import subprocess
import tempfile
from pathlib import Path


class LocalGuest:
    def __init__(self, strip_faketime=False, install_exit=0, fail_exec_after=None, raise_on_delete=False):
        self.dir = Path(tempfile.mkdtemp(prefix="tf-guest-"))
        self.strip_faketime = strip_faketime
        self.install_exit = install_exit
        self.fail_exec_after = fail_exec_after
        self.raise_on_delete = raise_on_delete
        self.commands, self.created, self.deleted = [], 0, 0

    def cli(self, arguments, input_text=None):
        op = arguments[0]
        if op == "create":
            self.created += 1
            return {"ok": True, "data": {"computer_id": f"local-{self.created}"}}
        if op == "delete":
            self.deleted += 1
            if self.raise_on_delete:
                return {"ok": False, "error": {"type": "CelestoError", "message": "x", "category": "transport"}}
            return {"ok": True, "data": {"computer_id": arguments[1]}}
        if op == "list":
            return {"ok": True, "data": {"computers": []}}
        assert op == "exec"
        command = arguments[-1]
        self.commands.append(command)
        if self.fail_exec_after is not None and len(self.commands) > self.fail_exec_after:
            return {"ok": False, "error": {"type": "OperationTimeoutError", "message": "timed out",
                                           "category": "transport", "ambiguous": True}}
        if command.startswith("set -eu; apt-get"):
            return {"ok": True, "data": {"exit_code": self.install_exit, "stdout": "", "stderr": "install failed" if self.install_exit else ""}}
        local = command.replace("/work", str(self.dir))
        if self.strip_faketime:
            import re
            local = re.sub(r'faketime "[^"]*" ', "", local)
        (self.dir).mkdir(exist_ok=True)
        r = subprocess.run(["sh", "-c", local], capture_output=True, text=True, timeout=120, cwd=self.dir)
        return {"ok": True, "data": {"exit_code": r.returncode, "stdout": r.stdout, "stderr": r.stderr}}
