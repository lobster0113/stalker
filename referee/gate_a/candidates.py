"""Built-in candidates for `--candidate referee.gate_a.candidates:<name>`.

Each takes the config {value_model, fgs_depth, tol, max_iter} and returns an `icm_reference.PolicyFn`.
"""
from __future__ import annotations

import numpy as np

from referee.anchors.icm_reference import HAND_CLASSES, N_CLASSES
from referee.gate_a.runner import nash_policy
from stalker.core.ranges import class_top_pct

TOP_PUSH, TOP_CALL = 0.30, 0.15


def reference(config):
    return nash_policy(config)


def top_percent(config):
    top = np.array([class_top_pct()[c] for c in HAND_CLASSES])
    push, call = (top <= TOP_PUSH).astype(float), (top <= TOP_CALL).astype(float)
    return lambda spot, seat, pusher: push if pusher is None else call


def always_fold(config):
    return lambda spot, seat, pusher: np.zeros(N_CLASSES)


def always_push(config):
    return lambda spot, seat, pusher: np.ones(N_CLASSES)
