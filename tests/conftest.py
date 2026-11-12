import os
import shutil

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


# The CI `numba` job installs `.[fast]`; gates does not, so a skip there would leave the
# numba path (the one training actually runs) untested again (#786).
REQUIRE_NUMBA = os.environ.get("STALKER_REQUIRE_NUMBA") == "1"


def _fail_numba(report):
    report.outcome = "failed"
    report.longrepr = (
        f"numba-marked test skipped under STALKER_REQUIRE_NUMBA=1: {report.longrepr}\n"
        'fix: install numba (python -m pip install -e ".[dev,fast]") or unset STALKER_REQUIRE_NUMBA'
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
    elif REQUIRE_NUMBA and report.skipped and item.get_closest_marker("numba") is not None:
        _fail_numba(report)


def node_path():
    """Path to node for the web node-suite wrappers (#436): skip locally without node, fail on CI."""
    path = shutil.which("node")
    if path is None:
        msg = "node not installed; install Node 22+ or run the suite with `node --test web/app/test/<suite>.test.mjs` where it is"
        if os.environ.get("CI") == "true":
            pytest.fail("CI=true but " + msg)
        pytest.skip(msg)
    return path


@pytest.fixture
def node():
    return node_path()
