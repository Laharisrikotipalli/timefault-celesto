import json
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from api import run_store  # noqa: E402
from api.scenarios import get_scenario  # noqa: E402
from api.run_store import serialize_run  # noqa: E402,F401


def read_runs():
    return run_store.list_runs()


def create_run(payload):
    scenario = payload.get("scenario_id", "unspecified")
    if not isinstance(scenario, str) or not scenario.strip():
        raise ValueError("scenario_id must be a non-empty string")

    scenario_id = scenario.strip()
    get_scenario(scenario_id)
    return run_store.create_run(scenario_id)


class Handler(BaseHTTPRequestHandler):
    def send_json(self, status, body):
        data = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/health":
            try:
                run_store.check_database()
                return self.send_json(200, {"status": "ok", "database": "ok"})
            except Exception:
                return self.send_json(503, {"status": "error", "database": "unavailable"})

        if path == "/api/runs":
            try:
                runs = read_runs()
                return self.send_json(200, {"runs": runs, "count": len(runs)})
            except Exception:
                return self.send_json(500, {"error": "database query failed"})

        prefix = "/api/runs/"
        if path.startswith(prefix):
            run_id = path[len(prefix):]
            try:
                run = run_store.get_run(run_id)
            except ValueError:
                run = None
            except Exception:
                return self.send_json(500, {"error": "database query failed"})
            if run is None:
                return self.send_json(404, {"error": "run not found"})
            return self.send_json(200, run)
        return self.send_json(404, {"error": "not found"})

    def do_POST(self):
        if urlparse(self.path).path != "/api/runs":
            return self.send_json(404, {"error": "not found"})

        try:
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                return self.send_json(400, {"error": "invalid request body size"})
            if length < 1 or length > 100_000:
                return self.send_json(400, {"error": "invalid request body size"})

            try:
                payload = json.loads(self.rfile.read(length))
            except (UnicodeDecodeError, json.JSONDecodeError):
                return self.send_json(400, {"error": "invalid JSON body"})
            if not isinstance(payload, dict):
                return self.send_json(400, {"error": "JSON object required"})

            run = create_run(payload)
            return self.send_json(201, run)
        except ValueError as exc:
            return self.send_json(400, {"error": str(exc)})
        except Exception:
            return self.send_json(500, {"error": "database operation failed"})

    def log_message(self, fmt, *args):
        print("%s - %s" % (self.log_date_time_string(), fmt % args))


if __name__ == "__main__":
    run_store.apply_migrations()
    port = int(os.environ.get("API_PORT", "8000"))
    server = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    print(f"TimeFault API listening on port {port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutdown requested")
    finally:
        server.server_close()
        print("HTTP server closed")
