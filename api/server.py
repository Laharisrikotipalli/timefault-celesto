import json
import os
import uuid
from datetime import timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

import psycopg
from psycopg.rows import dict_row

DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL environment variable is required")


def get_connection():
    return psycopg.connect(DATABASE_URL, row_factory=dict_row)


def serialize_run(row):
    return {
        "run_id": str(row["run_id"]),
        "scenario_id": row["scenario_id"],
        "status": row["status"],
        "created_at": row["created_at"].astimezone(timezone.utc).isoformat(),
    }


def read_runs():
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT run_id, scenario_id, status, created_at
            FROM runs
            ORDER BY created_at DESC
            """
        ).fetchall()
    return [serialize_run(row) for row in rows]


def create_run(payload):
    scenario = payload.get("scenario_id", "unspecified")
    if not isinstance(scenario, str) or not scenario.strip():
        raise ValueError("scenario_id must be a non-empty string")

    run_id = uuid.uuid4()
    with get_connection() as conn:
        row = conn.execute(
            """
            INSERT INTO runs (run_id, scenario_id, status)
            VALUES (%s, %s, 'queued')
            RETURNING run_id, scenario_id, status, created_at
            """,
            (run_id, scenario.strip()),
        ).fetchone()
    return serialize_run(row)


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
                with get_connection() as conn:
                    conn.execute("SELECT 1")
                return self.send_json(200, {"status": "ok", "database": "ok"})
            except Exception:
                return self.send_json(503, {"status": "error", "database": "unavailable"})

        if path == "/api/runs":
            try:
                runs = read_runs()
                return self.send_json(200, {"runs": runs, "count": len(runs)})
            except Exception:
                return self.send_json(500, {"error": "database query failed"})
        return self.send_json(404, {"error": "not found"})

    def do_POST(self):
        if urlparse(self.path).path != "/api/runs":
            return self.send_json(404, {"error": "not found"})

        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length < 1 or length > 100_000:
                return self.send_json(400, {"error": "invalid request body size"})

            payload = json.loads(self.rfile.read(length))
            if not isinstance(payload, dict):
                return self.send_json(400, {"error": "JSON object required"})

            run = create_run(payload)
            return self.send_json(201, run)
        except (ValueError, json.JSONDecodeError) as exc:
            return self.send_json(400, {"error": str(exc)})
        except Exception:
            return self.send_json(500, {"error": "database operation failed"})

    def log_message(self, fmt, *args):
        print("%s - %s" % (self.log_date_time_string(), fmt % args))


if __name__ == "__main__":
    port = int(os.environ.get("API_PORT", "8000"))
    server = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    print(f"TimeFault API listening on port {port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\\nShutdown requested")
    finally:
        server.server_close()
        print("HTTP server closed")
