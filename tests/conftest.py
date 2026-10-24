import os

import pytest

# The CI `rl` job installs torch; a torch skip there means the RL acceptance
# criteria would silently rest on local runs only (issue #51).
REQUIRE_TORCH = os.environ.get("STALKER_REQUIRE_TORCH") == "1"


def _torch_skip(report):
    if not (REQUIRE_TORCH and report.skipped):
        return False
    # Skip longrepr is (path, lineno, message); match the message only, not the path.
    reason = report.longrepr[-1] if isinstance(report.longrepr, tuple) else report.longrepr
    return "torch" in str(reason).lower()


def _fail(report):
    report.outcome = "failed"
    report.longrepr = (
        f"torch test skipped under STALKER_REQUIRE_TORCH=1: {report.longrepr}\n"
        'fix: install torch (python -m pip install -e ".[dev,rl]") or unset STALKER_REQUIRE_TORCH'
    )


@pytest.hookimpl(hookwrapper=True)
def pytest_make_collect_report(collector):
    outcome = yield
    report = outcome.get_result()
    if _torch_skip(report):
        _fail(report)


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    report = outcome.get_result()
    if _torch_skip(report):
        _fail(report)
