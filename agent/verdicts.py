def classify(status):
    """Classify observed outcomes conservatively."""
    if not status:
        return "env_failure"

    if any(
        result in {"env_error", "time_control_error"}
        for result in status.values()
    ):
        return "env_failure"

    if any(result == "flaky" for result in status.values()):
        return "inconclusive"

    failures = [
        day for day, result in status.items()
        if result == "fail"
    ]
    passes = [
        day for day, result in status.items()
        if result == "pass"
    ]

    if failures and not passes:
        return "inconclusive"

    if failures and passes:
        return "date_bug_candidate"

    if passes and not failures:
        return "clean"

    return "inconclusive"
