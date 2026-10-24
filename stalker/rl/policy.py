"""Small recurrent actor-critic that knows game boundaries (ADR 0003/0006). Requires the optional `[rl]` extra (torch).

Variants (`PolicyConfig.variant`): ai0 = no game memory, ai1 = opponent statistics from GameMemory, ai2 = statistics +
a GRU carried across the decisions of one game. `forward` is pure (the GRU state goes in and out); `act` keeps the
state on the policy, and `reset_memory()` must be called at every game boundary (Gate L6).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import NamedTuple

import numpy as np
import torch
from torch import nn

from stalker.observe.builder import HeroObservation
from stalker.rl.features import CARD_DIM, GLOBAL_DIM, SEAT_DIM, encode

VARIANTS = ("ai0", "ai1", "ai2")


@dataclass(frozen=True)
class PolicyConfig:
    variant: str = "ai2"
    n_actions: int = 5  # fold, call, raises..., all-in: must equal TournamentEnv.n_actions
    d_model: int = 64
    n_heads: int = 4
    gru_hidden: int = 64

    def __post_init__(self) -> None:
        if self.variant not in VARIANTS:
            raise ValueError(f"variant must be one of {VARIANTS}, got {self.variant!r}.")
        if self.n_actions < 3:
            raise ValueError("n_actions must be at least 3 (fold, call, all-in).")


class PolicyOutput(NamedTuple):
    probs: torch.Tensor  # (B, n_actions); exactly 0 where the mask is False
    logits: torch.Tensor  # masked logits (-inf where illegal)
    value: torch.Tensor  # (B,)
    state: torch.Tensor | None  # new GRU state (B, gru_hidden) for ai2, else None


class Policy(nn.Module):
    def __init__(self, config: PolicyConfig | None, seed: int) -> None:
        super().__init__()
        # Weight init draws from torch's global RNG; fork it so the seed alone decides the weights and the
        # caller's global RNG state is left untouched (CLAUDE.md: no global randomness).
        with torch.random.fork_rng(devices=[]):
            torch.manual_seed(seed)
            self._build(config or PolicyConfig())

    def _build(self, cfg: PolicyConfig) -> None:
        self.config = cfg
        d = cfg.d_model
        self.seat_in = nn.Sequential(nn.Linear(SEAT_DIM, d), nn.ReLU(), nn.Linear(d, d))
        self.slot_emb = nn.Embedding(9, d)  # slot 0 = hero, then clockwise
        self.encoder = nn.TransformerEncoder(
            nn.TransformerEncoderLayer(d, cfg.n_heads, 2 * d, dropout=0.0, batch_first=True), num_layers=1,
            enable_nested_tensor=False)
        self.card_in = nn.Sequential(nn.Linear(CARD_DIM, d), nn.ReLU())
        self.glob_in = nn.Sequential(nn.Linear(GLOBAL_DIM, d), nn.ReLU())
        self.trunk_in = 4 * d  # hero token, seat mean, cards, global
        self.gru = nn.GRUCell(self.trunk_in, cfg.gru_hidden) if cfg.variant == "ai2" else None
        head_in = self.trunk_in + (cfg.gru_hidden if self.gru is not None else 0)
        self.trunk = nn.Sequential(nn.Linear(head_in, 2 * d), nn.ReLU())
        self.actor = nn.Linear(2 * d, cfg.n_actions)
        self.critic = nn.Linear(2 * d, 1)
        self._state: torch.Tensor | None = None

    @property
    def uses_stats(self) -> bool:
        return self.config.variant != "ai0"

    def initial_state(self, batch: int = 1) -> torch.Tensor | None:
        return None if self.gru is None else torch.zeros(batch, self.config.gru_hidden)

    def forward(self, batch: dict[str, torch.Tensor], action_mask: torch.Tensor,
                state: torch.Tensor | None = None) -> PolicyOutput:
        if not bool(action_mask.any(dim=-1).all()):
            raise ValueError("every row needs at least one legal action in action_mask.")
        seat_mask = batch["seat_mask"]
        x = self.seat_in(batch["seats"]) + self.slot_emb.weight[: seat_mask.shape[1]]
        x = self.encoder(x, src_key_padding_mask=~seat_mask)
        m = seat_mask.unsqueeze(-1).float()
        seat_mean = (x * m).sum(1) / m.sum(1).clamp(min=1.0)
        cm = batch["card_mask"].unsqueeze(-1).float()
        cards = (self.card_in(batch["cards"]) * cm).sum(1) / cm.sum(1).clamp(min=1.0)
        z = torch.cat([x[:, 0], seat_mean, cards, self.glob_in(batch["glob"])], dim=-1)
        new_state = None
        if self.gru is not None:
            h = self.initial_state(z.shape[0]) if state is None else state
            new_state = self.gru(z, h)
            z = torch.cat([z, new_state], dim=-1)
        h = self.trunk(z)
        logits = self.actor(h).masked_fill(~action_mask, float("-inf"))
        return PolicyOutput(torch.softmax(logits, dim=-1), logits, self.critic(h).squeeze(-1), new_state)

    def collate(self, observations: list[HeroObservation]) -> dict[str, torch.Tensor]:
        feats = [encode(o, with_stats=self.uses_stats) for o in observations]
        return {k: torch.from_numpy(np.stack([f[k] for f in feats])) for k in feats[0]}

    def reset_memory(self) -> None:
        self._state = None

    @torch.no_grad()
    def act(self, observation: HeroObservation, action_mask: tuple[bool, ...]) -> PolicyOutput:
        """One decision of the current game; the GRU state advances unless the variant has none."""
        out = self.forward(self.collate([observation]), torch.tensor([action_mask], dtype=torch.bool), self._state)
        self._state = out.state
        return out
