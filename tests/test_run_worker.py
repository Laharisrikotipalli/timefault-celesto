
import json
import unittest
from datetime import datetime, timezone
from unittest.mock import Mock, patch

from agent import run_service, worker
from api import run_store, server
from api.scenarios import get_scenario


class FakeResult:
    def __init__(self, row):
        self.row = row

    def fetchone(self):
        return self.row


class FakeConnection:
    def __init__(self, row):
        self.row = row
        self.queries = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, query, params=None):
        self.queries.append((query, params))
        return FakeResult(self.row)


class RunStoreTests(unittest.TestCase):
    def setUp(self):
        self.run_row = {
            "run_id": "8e3385f6-a00c-49d0-8712-78e8046e752c",
            "scenario_id": "E01",
            "status": "running",
            "created_at": datetime(2026, 10, 24, tzinfo=timezone.utc),
            "result": None,
            "error": None,
        }

    def test_claim_uses_row_lock_and_transitions_to_running(self):
        conn = FakeConnection(
            {"run_id": self.run_row["run_id"], "scenario_id": "E01"}
        )

        with patch.object(run_store, "get_connection", return_value=conn):
            claimed = run_store.claim_next_run()

        self.assertEqual(claimed["scenario_id"], "E01")
        self.assertIn("FOR UPDATE SKIP LOCKED", conn.queries[0][0])
        self.assertIn("SET status = 'running'", conn.queries[1][0])
        self.assertIn("status = 'queued'", conn.queries[1][0])

    def test_empty_queue_returns_none(self):
        conn = FakeConnection(None)

        with patch.object(run_store, "get_connection", return_value=conn):
            self.assertIsNone(run_store.claim_next_run())

        self.assertEqual(len(conn.queries), 1)

    def test_completion_persists_result_as_json(self):
        conn = FakeConnection({"run_id": self.run_row["run_id"]})
        result = {
            "investigation": {"verdict": "clean"},
            "score": {"label_ok": True},
        }

        with patch.object(run_store, "get_connection", return_value=conn):
            run_store.complete_run(self.run_row["run_id"], result)

        query, params = conn.queries[0]
        self.assertIn(
            "SET status = %s, result = %s::jsonb, error = %s",
            query,
        )
        self.assertEqual(params[0], "completed")
        self.assertEqual(json.loads(params[1]), result)
        self.assertIsNone(params[2])

    def test_failure_persists_safe_error_and_failed_status(self):
        conn = FakeConnection({"run_id": self.run_row["run_id"]})

        with patch.object(run_store, "get_connection", return_value=conn):
            run_store.fail_run(
                self.run_row["run_id"],
                worker.SAFE_FAILURE_MESSAGE,
            )

        _, params = conn.queries[0]
        self.assertEqual(params[0], "failed")
        self.assertIsNone(params[1])
        self.assertEqual(params[2], worker.SAFE_FAILURE_MESSAGE)

    def test_migration_only_adds_nullable_result_and_error_columns(self):
        migration = run_store.ROOT / "seeds" / "02_run_results.sql"

        statements = [
            statement.strip()
            for statement in migration.read_text().split(";")
            if statement.strip()
        ]

        self.assertEqual(len(statements), 2)
        self.assertTrue(
            all(
                "ADD COLUMN IF NOT EXISTS" in statement
                for statement in statements
            )
        )
        self.assertTrue(
            all("DROP " not in statement.upper() for statement in statements)
        )


class WorkerTests(unittest.TestCase):
    def test_process_one_persists_actual_executor_result(self):
        actual_result = {
            "investigation": {"verdict": "date_bug_candidate"}
        }

        with (
            patch.object(
                worker.run_store,
                "claim_next_run",
                return_value={"run_id": "run-1", "scenario_id": "E01"},
            ),
            patch.object(
                worker,
                "run_investigation",
                return_value=actual_result,
            ),
            patch.object(worker.run_store, "complete_run") as complete,
            patch.object(worker.run_store, "fail_run") as fail,
        ):
            self.assertTrue(
                worker.process_one(allowed_scenarios=["E01"])
            )

        complete.assert_called_once_with("run-1", actual_result)
        fail.assert_not_called()

    def test_process_one_marks_executor_failure_without_exposing_exception(self):
        with (
            patch.object(
                worker.run_store,
                "claim_next_run",
                return_value={"run_id": "run-2", "scenario_id": "E01"},
            ),
            patch.object(
                worker,
                "run_investigation",
                side_effect=RuntimeError(
                    "credential=must-not-be-returned"
                ),
            ),
            patch.object(worker.run_store, "complete_run") as complete,
            patch.object(worker.run_store, "fail_run") as fail,
        ):
            self.assertTrue(
                worker.process_one(allowed_scenarios=["E01"])
            )

        complete.assert_not_called()
        fail.assert_called_once_with(
            "run-2",
            worker.SAFE_FAILURE_MESSAGE,
        )

    def test_empty_queue_does_not_execute_or_complete_a_run(self):
        with (
            patch.object(
                worker.run_store,
                "claim_next_run",
                return_value=None,
            ),
            patch.object(worker, "run_investigation") as execute,
            patch.object(worker.run_store, "complete_run") as complete,
        ):
            self.assertFalse(
                worker.process_one(allowed_scenarios=["E01"])
            )

        execute.assert_not_called()
        complete.assert_not_called()


class ScenarioAndApiTests(unittest.TestCase):
    def test_scenario_must_exist_in_oracle_and_fixture_tree(self):
        self.assertEqual(
            get_scenario("E01")["oracle"]["scenario_id"],
            "E01",
        )

        with self.assertRaises(ValueError):
            get_scenario("../../seeds/01_runs.sql")

    def test_api_rejects_unknown_scenario_before_database_insert(self):
        with patch.object(server.run_store, "create_run") as create:
            with self.assertRaises(ValueError):
                server.create_run({"scenario_id": "not-a-fixture"})

        create.assert_not_called()

    def test_individual_run_endpoint_returns_persisted_run_details(self):
        run = {
            "run_id": "8e3385f6-a00c-49d0-8712-78e8046e752c",
            "scenario_id": "E01",
            "status": "completed",
            "created_at": "2026-10-24T00:00:00+00:00",
            "result": {"investigation": {"verdict": "clean"}},
            "error": None,
        }

        handler = object.__new__(server.Handler)
        handler.path = f"/api/runs/{run['run_id']}"
        handler.send_json = Mock()

        with patch.object(server.run_store, "get_run", return_value=run):
            server.Handler.do_GET(handler)

        handler.send_json.assert_called_once_with(200, run)


class CelestoCleanupTests(unittest.TestCase):
    def _mock_engine(self, investigate_result):
        return (
            patch.object(
                run_service,
                "get_scenario",
                return_value={
                    "oracle": {"expected_label": "clean"},
                    "source": "print('ok')\n",
                },
            ),
            patch.object(
                run_service.run_one,
                "cli",
                side_effect=[
                    {
                        "ok": True,
                        "data": {"computer_id": "celesto-computer-1"},
                    },
                    {"ok": True, "data": {}},
                ],
            ),
            patch.object(
                run_service.investigate,
                "gexec",
                side_effect=[
                    {"exit_code": 0},
                    {"exit_code": 0, "stdout": "2028-02-29\n"},
                    {"exit_code": 0},
                ],
            ),
            patch.object(
                run_service.investigate,
                "investigate",
                return_value=investigate_result,
            ),
            patch.object(
                run_service.investigate,
                "score",
                return_value={"label_ok": True},
            ),
        )

    def test_created_computer_is_deleted_after_success(self):
        investigation = {"verdict": "clean"}
        patches = self._mock_engine(investigation)

        with (
            patches[0],
            patches[1] as cli,
            patches[2],
            patches[3],
            patches[4],
        ):
            result = run_service.run_investigation("E01")

        self.assertEqual(result["investigation"], investigation)

        cli.assert_any_call(
            ["delete", "celesto-computer-1"],
            input_text="y\n",
        )

        self.assertEqual(run_service.run_one.MAP, {})

    def test_computer_id_is_cleaned_up_even_if_create_reports_failure(self):
        with (
            patch.object(
                run_service,
                "get_scenario",
                return_value={
                    "oracle": {"expected_label": "clean"},
                    "source": "print('ok')\n",
                },
            ),
            patch.object(
                run_service.run_one,
                "cli",
                side_effect=[
                    {
                        "ok": False,
                        "data": {"computer_id": "celesto-computer-1"},
                    },
                    {"ok": True, "data": {}},
                ],
            ) as cli,
        ):
            with self.assertRaisesRegex(RuntimeError, "creation failed"):
                run_service.run_investigation("E01")

        cli.assert_any_call(
            ["delete", "celesto-computer-1"],
            input_text="y\n",
        )

        self.assertEqual(run_service.run_one.MAP, {})

    def test_created_computer_is_deleted_when_investigation_fails(self):
        create_response = {
            "ok": True,
            "data": {"computer_id": "celesto-computer-1"},
        }
        delete_response = {"ok": True, "data": {}}

        with (
            patch.object(
                run_service,
                "get_scenario",
                return_value={
                    "oracle": {"expected_label": "clean"},
                    "source": "print('ok')\n",
                },
            ),
            patch.object(
                run_service.run_one,
                "cli",
                side_effect=[create_response, delete_response],
            ) as cli,
            patch.object(
                run_service.investigate,
                "gexec",
                side_effect=[
                    {"exit_code": 0},
                    {"exit_code": 0, "stdout": "2028-02-29\n"},
                    {"exit_code": 0},
                ],
            ),
            patch.object(
                run_service.investigate,
                "investigate",
                side_effect=RuntimeError("private credential detail"),
            ),
        ):
            with self.assertRaisesRegex(
                RuntimeError,
                "private credential detail",
            ):
                run_service.run_investigation("E01")

        cli.assert_any_call(
            ["delete", "celesto-computer-1"],
            input_text="y\n",
        )

        self.assertEqual(run_service.run_one.MAP, {})


if __name__ == "__main__":
    unittest.main()
