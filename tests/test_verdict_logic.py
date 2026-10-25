import unittest
from agent.verdicts import classify


class VerdictLogicTests(unittest.TestCase):
    def test_all_fail_is_inconclusive(self):
        self.assertEqual(
            classify({"2028-02-28": "fail", "2028-02-29": "fail"}),
            "inconclusive",
        )

    def test_all_pass(self):
        self.assertEqual(
            classify({"2028-02-28": "pass", "2028-02-29": "pass"}),
            "clean",
        )

    def test_environment_failure(self):
        self.assertEqual(
            classify({"2028-02-28": "pass", "2028-02-29": "time_control_error"}),
            "env_failure",
        )

    def test_flaky_is_inconclusive(self):
        self.assertEqual(
            classify({"2028-02-28": "pass", "2028-02-29": "flaky"}),
            "inconclusive",
        )

    def test_mixed_results_are_only_a_candidate(self):
        self.assertEqual(
            classify({"2028-02-28": "pass", "2028-02-29": "fail"}),
            "date_bug_candidate",
        )


if __name__ == "__main__":
    unittest.main()
