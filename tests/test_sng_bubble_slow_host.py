"""#941: sng-bubble training jobs declare median_iters_per_s so the launcher replaces slow hosts (F6b saw 3 of 5)."""
import pytest

from tests.test_cloud_launcher import L, ROOT

JOBS = sorted((ROOT / "jobs").glob("e3-tp-mid-c1-sng-bubble-*pod32.yaml"))
# F6b observed it/s (ops:cloud/results summaries; non-CI reference values): slow cpu3c hosts and normal hosts.
SLOWEST_SLOW, SLOWEST_NORMAL = 6.25, 11.36


def test_all_seven_training_jobs_found():   # #996 added the BB-ante job
    assert len(JOBS) == 7


@pytest.mark.parametrize("path", JOBS, ids=lambda p: p.stem)
def test_threshold_separates_slow_from_normal_hosts(path):
    job = L.load_spec(path)
    (_, _, median), = job.flavors
    assert median > 0, "median_iters_per_s missing: slow-host replacement stays off"
    threshold = L.SLOW_HOST_FRACTION * median
    assert SLOWEST_SLOW < threshold < SLOWEST_NORMAL


@pytest.mark.parametrize("path", JOBS, ids=lambda p: p.stem)
def test_other_fields_unchanged(path):
    job = L.load_spec(path)
    assert (job.cpu_flavor, job.vcpu, job.disk_gb, job.max_minutes, job.hourly_usd) == ("cpu3c", 32, 10, 180, 1.2)
    assert job.worst_case_usd == 3.6
