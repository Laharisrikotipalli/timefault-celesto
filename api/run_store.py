import json
import os
import uuid
from datetime import timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def get_connection():
    import psycopg
    from psycopg.rows import dict_row

    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL environment variable is required")
    return psycopg.connect(database_url, row_factory=dict_row)


def serialize_run(row):
    return {
        "run_id": str(row["run_id"]),
        "scenario_id": row["scenario_id"],
        "status": row["status"],
        "created_at": row["created_at"].astimezone(timezone.utc).isoformat(),
        "result": row.get("result"),
        "error": row.get("error"),
    }


def apply_migrations():
    migration = ROOT / "seeds" / "02_run_results.sql"
    statements = [statement.strip() for statement in migration.read_text().split(";")]
    with get_connection() as conn:
        for statement in statements:
            if statement:
                conn.execute(statement)


def check_database():
    with get_connection() as conn:
        conn.execute("SELECT 1")


def list_runs():
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT run_id, scenario_id, status, created_at, result, error
            FROM runs
            ORDER BY created_at DESC
            """
        ).fetchall()
    return [serialize_run(row) for row in rows]


def get_run(run_id):
    try:
        parsed_id = uuid.UUID(run_id)
    except (TypeError, ValueError, AttributeError) as exc:
        raise ValueError("invalid run id") from exc
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT run_id, scenario_id, status, created_at, result, error
            FROM runs
            WHERE run_id = %s
            """,
            (parsed_id,),
        ).fetchone()
    return serialize_run(row) if row else None


def create_run(scenario_id):
    with get_connection() as conn:
        row = conn.execute(
            """
            INSERT INTO runs (run_id, scenario_id, status)
            VALUES (%s, %s, 'queued')
            RETURNING run_id, scenario_id, status, created_at, result, error
            """,
            (uuid.uuid4(), scenario_id),
        ).fetchone()
    return serialize_run(row)


def claim_next_run(allowed_scenarios=None):
    with get_connection() as conn:
        if allowed_scenarios:
            row = conn.execute(
                """
                SELECT run_id, scenario_id
                FROM runs
                WHERE status = 'queued'
                  AND scenario_id = ANY(%s)
                ORDER BY created_at
                LIMIT 1
                FOR UPDATE SKIP LOCKED
                """,
                (allowed_scenarios,),
            ).fetchone()
        else:
            row = conn.execute(
                """
                SELECT run_id, scenario_id
                FROM runs
                WHERE status = 'queued'
                ORDER BY created_at
                LIMIT 1
                FOR UPDATE SKIP LOCKED
                """
            ).fetchone()

        if row is None:
            return None

        claimed = conn.execute(
            """
            UPDATE runs
            SET status = 'running', result = NULL, error = NULL
            WHERE run_id = %s AND status = 'queued'
            RETURNING run_id, scenario_id
            """,
            (row["run_id"],),
        ).fetchone()

    return claimed


def complete_run(run_id, result):
    return _finish_run(run_id, "completed", json.dumps(result), None)


def fail_run(run_id, error):
    return _finish_run(run_id, "failed", None, error)


def _finish_run(run_id, status, result, error):
    with get_connection() as conn:
        row = conn.execute(
            """
            UPDATE runs
            SET status = %s, result = %s::jsonb, error = %s
            WHERE run_id = %s AND status = 'running'
            RETURNING run_id
            """,
            (status, result, error, run_id),
        ).fetchone()
    if row is None:
        raise RuntimeError("run is no longer in the running state")
    return row
