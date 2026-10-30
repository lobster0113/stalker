"""#436: the web node-suite wrappers skip without node locally but fail on CI, so CI never skips them silently."""
import shutil

import pytest
from conftest import node_path


def test_missing_node_fails_on_ci(monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda name: None)
    monkeypatch.setenv("CI", "true")
    with pytest.raises(pytest.fail.Exception, match="CI=true"):
        node_path()


def test_missing_node_skips_locally(monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda name: None)
    monkeypatch.delenv("CI", raising=False)
    with pytest.raises(pytest.skip.Exception):
        node_path()


def test_found_node_is_returned(monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda name: "/usr/bin/node")
    assert node_path() == "/usr/bin/node"
