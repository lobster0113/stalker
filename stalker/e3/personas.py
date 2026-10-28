"""Persona field for E3 6-max (#295): the E2 persona rules (#226) on the E3 action menu.

E3 uses the E2 action labels (stalker/e3/game.py), so the rules carry over unchanged: a persona reads
only its own cards and the public state, is deterministic, and returns probabilities over
`stalker.e3.game.legal(state)`; a label the menu does not offer falls back as in E2. The VPIP
targets were calibrated for 6-max, so here they read as frequencies. Personas are baselines and
evaluation opponents only, never the TP-GTO (user requirement).
"""
from __future__ import annotations

from stalker.agents.persona import PRESETS, PersonaParams
from stalker.e2.personas import Persona as _E2Persona
from stalker.e3 import game as G


class Persona(_E2Persona):
    legal = staticmethod(G.legal)

    def __init__(self, name: str, params: PersonaParams | None = None):
        super().__init__(name, params)


def field(names=None) -> list[Persona]:
    return [Persona(n) for n in (names or PRESETS)]
