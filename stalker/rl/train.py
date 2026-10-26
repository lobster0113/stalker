"""Recurrent PPO over `TournamentEnv` self-play (ADR 0003). Requires the optional `[rl]` extra (torch).

Seats are played by the learning policy (self-play), except an opponent pool drawn anew each game, whose seats
produce no training data: `TrainConfig.random_seats` scripted random players (`random_action`, the `RandomLegalAgent`
rule), `reference_seats` Gate B reference bots v1 (`ReferenceBot`), and, once `past_checkpoints` > 0 has stored
snapshots, each remaining seat but one with probability `past_checkpoint_p` a frozen past policy (`PolicyAgent`). A trajectory
is one `Segment` = one player's decisions in one game (`game_id`, `player_id`); the GRU state starts from zeros at the first step of every segment, both while acting
and when the update replays the segment, so no state crosses a game boundary (Gate L6, `check_segments`).
Reward = (prize - buy_in) / buy_in at the last step of the segment (payout-normalised, ADR 0003 §4).

Randomness: actions and minibatch order come from one `numpy.random.Generator` seeded by `TrainConfig.seed`,
weights from `Policy(config, seed)`; torch's global RNG is never drawn, so the same seed gives the same weights.
"""
from __future__ import annotations

import copy
import hashlib
import io
from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np
import torch

from referee.agents.reference_bot import ReferenceBot
from stalker.agents.base import Action, Agent, Event, Observation
from stalker.observe.builder import HeroObservation, ObservationBuilder
from stalker.observe.memory import GameMemoryStore
from stalker.rl.env import DEFAULT_RAISE_FRACTIONS, GAME_START, TournamentEnv, action_mask, index_to_action
from stalker.rl.policy import Policy, PolicyConfig
from stalker.tournament.config import TournamentConfig


@dataclass(frozen=True)
class TrainConfig:
    seed: int = 0
    variant: str = "ai2"
    games_per_iter: int = 4
    epochs: int = 2
    minibatch_segments: int = 8
    lr: float = 3e-4
    gamma: float = 1.0
    gae_lambda: float = 0.95
    clip: float = 0.2
    value_coef: float = 0.5
    entropy_coef: float = 0.01
    max_grad_norm: float = 0.5
    raise_pot_fractions: tuple[float, ...] = DEFAULT_RAISE_FRACTIONS
    random_seats: int = 0  # seats per game (drawn anew each game) played by `random_action` instead of the policy
    reference_seats: int = 0  # seats per game played by the Gate B reference bot v1
    past_checkpoints: int = 0  # snapshot the policy every N iterations into the opponent pool (0 = off)
    past_checkpoint_p: float = 0.5  # chance that a non-pool seat (all but one learner seat) gets a past snapshot
    past_pool_size: int = 5  # most recent snapshots kept


@dataclass
class Segment:
    """One player's decisions in one game; the unit the update replays from a zero GRU state."""

    game_id: str
    player_id: int
    observations: list[HeroObservation] = field(default_factory=list)
    masks: list[tuple[bool, ...]] = field(default_factory=list)
    actions: list[int] = field(default_factory=list)
    logps: list[float] = field(default_factory=list)
    values: list[float] = field(default_factory=list)
    initial_state_zero: bool = True  # recorded at the first decision; check_segments asserts it
    reward: float = 0.0


def check_segments(segments: list[Segment]) -> None:
    """Gate L6 for a training batch: one game_id per segment, every segment starts from a zero state, no duplicates."""
    keys = set()
    for s in segments:
        key = (s.game_id, s.player_id)
        if key in keys:
            raise ValueError(f"segment {key} appears twice; split trajectories by (game_id, player_id).")
        keys.add(key)
        if any(o.game_id != s.game_id for o in s.observations):
            raise ValueError(f"segment {key} mixes observations of other games; cut trajectories at game_id.")
        if not s.initial_state_zero:
            raise ValueError(f"segment {key} did not start from a zero GRU state; reset_memory at game start.")


def advantages(values: np.ndarray, reward: float, gamma: float, lam: float) -> tuple[np.ndarray, np.ndarray]:
    """GAE over one segment whose only reward arrives after its last step (terminal value 0)."""
    n = len(values)
    adv = np.zeros(n, dtype=np.float32)
    nxt, last = 0.0, 0.0
    for t in reversed(range(n)):
        r = reward if t == n - 1 else 0.0
        delta = r + gamma * nxt - values[t]
        last = delta + gamma * lam * last
        adv[t] = last
        nxt = values[t]
    return adv, adv + values.astype(np.float32)


def policy_version(policy: Policy, iteration: int) -> str:
    """`<variant>-i<iteration>-<weights sha256[:8]>`: names the exact weights that produced a decision record."""
    h = hashlib.sha256()
    for k, v in sorted(policy.state_dict().items()):
        h.update(k.encode())
        h.update(v.detach().numpy().tobytes())
    return f"{policy.config.variant}-i{iteration}-{h.hexdigest()[:8]}"


def random_action(hero: HeroObservation, mask: tuple[bool, ...], rng: np.random.Generator,
                  fold_p: float = 0.2, raise_p: float = 0.25) -> int:
    """`RandomLegalAgent`'s rule over ActionSpec indices: fold only facing a bet, raises spread over the raise entries."""
    r = rng.random()
    if mask[0] and hero.legal["call_amount"] > 0 and r < fold_p:
        return 0
    raises = [i for i in range(2, len(mask)) if mask[i]]
    if raises and r > 1 - raise_p:
        return int(rng.choice(raises))
    return 1


class Trainer:
    def __init__(self, env_config: TournamentConfig, config: TrainConfig | None = None) -> None:
        self.config = cfg = config or TrainConfig()
        if min(cfg.random_seats, cfg.reference_seats, cfg.past_checkpoints) < 0:
            raise ValueError("random_seats, reference_seats and past_checkpoints must be >= 0.")
        if cfg.random_seats + cfg.reference_seats >= env_config.players:
            raise ValueError(f"random_seats + reference_seats = {cfg.random_seats + cfg.reference_seats} leaves no "
                             f"learning seat among {env_config.players} players; lower them.")
        self.env_config = env_config
        self.env = TournamentEnv(env_config, cfg.raise_pot_fractions)
        self.policy = Policy(PolicyConfig(variant=cfg.variant, n_actions=self.env.n_actions), cfg.seed)
        self.optimizer = torch.optim.Adam(self.policy.parameters(), lr=cfg.lr)
        self.rng = np.random.default_rng(cfg.seed)
        self.iteration = 0
        self.games_played = 0
        self.past_pool: list[Policy] = []  # frozen snapshots, oldest first

    @property
    def policy_version(self) -> str:
        return policy_version(self.policy, self.iteration)

    # ---- rollout ----
    @torch.no_grad()
    def play_game(self, game_id: str) -> list[Segment]:
        segs: dict[int, Segment] = {}
        states: dict[int, torch.Tensor | None] = {}
        scripted = set(self.rng.choice(self.env_config.players, self.config.random_seats, replace=False).tolist())
        res = self.env.reset(self.rng, game_id, self._pool_agents(scripted))
        while not res.done:
            if GAME_START in res.events:
                states = {}  # L6: no GRU state survives into a new game
            pid = res.player_id
            if pid in scripted:
                res = self.env.step(random_action(res.observation, res.action_mask, self.rng))
                continue
            seg = segs.setdefault(pid, Segment(game_id, pid))
            if not seg.observations:
                seg.initial_state_zero = pid not in states
            out = self.policy(self.policy.collate([res.observation]),
                              torch.tensor([res.action_mask], dtype=torch.bool), states.get(pid))
            states[pid] = out.state
            probs = out.probs[0].double().numpy()
            a = int(self.rng.choice(len(probs), p=probs / probs.sum()))
            seg.observations.append(res.observation)
            seg.masks.append(res.action_mask)
            seg.actions.append(a)
            seg.logps.append(float(torch.log(out.probs[0, a])))
            seg.values.append(float(out.value[0]))
            res = self.env.step(a)
        for pid, seg in segs.items():  # scripted seats have no segment: they are not trained
            seg.reward = res.rewards[pid] / self.env_config.buy_in
        self.games_played += 1
        return list(segs.values())

    def _pool_agents(self, scripted: set[int]) -> dict[int, Agent]:
        """Reference-bot and past-snapshot seats for one game. Draws nothing from `rng` when the pool is off, so
        a config without the pool reproduces the earlier trajectories exactly."""
        cfg = self.config
        if not cfg.reference_seats and not self.past_pool:
            return {}
        rest = [p for p in range(self.env_config.players) if p not in scripted]
        rest = [rest[i] for i in self.rng.permutation(len(rest))]
        agents: dict[int, Agent] = {}
        payouts = self.env_config.payout_ratios()
        for p in rest[:cfg.reference_seats]:
            agents[p] = ReferenceBot(self._child_rng(), payouts)
        if self.past_pool:
            for p in rest[cfg.reference_seats + 1:]:  # the first remaining seat always learns
                if self.rng.random() < cfg.past_checkpoint_p:
                    past = self.past_pool[int(self.rng.integers(len(self.past_pool)))]
                    agents[p] = PolicyAgent(past, self.env_config, self._child_rng(), cfg.raise_pot_fractions)
        return agents

    def _child_rng(self) -> np.random.Generator:
        return np.random.default_rng(int(self.rng.integers(2**63)))

    # ---- update ----
    def _replay(self, segs: list[Segment]):
        """Re-run segments step by step from zero states, batched across segments (padded by step index)."""
        n = max(len(s.actions) for s in segs)
        feats = [self.policy.collate(s.observations) for s in segs]
        state = self.policy.initial_state(len(segs))
        logps, values, ents, valid = [], [], [], []
        for t in range(n):
            rows = [min(t, len(s.actions) - 1) for s in segs]
            batch = {k: torch.stack([f[k][r] for f, r in zip(feats, rows)]) for k in feats[0]}
            mask = torch.tensor([s.masks[r] for s, r in zip(segs, rows)], dtype=torch.bool)
            act = torch.tensor([s.actions[r] for s, r in zip(segs, rows)])
            out = self.policy(batch, mask, state)
            state = out.state
            lp = torch.log_softmax(out.logits, -1)
            logps.append(lp.gather(1, act[:, None]).squeeze(1))
            p = out.probs
            ents.append(-(p * torch.where(p > 0, lp, torch.zeros_like(lp))).sum(-1))
            values.append(out.value)
            valid.append(torch.tensor([t < len(s.actions) for s in segs]))
        return torch.stack(logps, 1), torch.stack(values, 1), torch.stack(ents, 1), torch.stack(valid, 1)

    def update(self, segments: list[Segment]) -> dict[str, float]:
        check_segments(segments)
        cfg = self.config
        gae = [advantages(np.array(s.values), s.reward, cfg.gamma, cfg.gae_lambda) for s in segments]
        flat_adv = np.concatenate([a for a, _ in gae])
        mean, std = float(flat_adv.mean()), float(flat_adv.std()) + 1e-8
        stats = {"loss": 0.0, "policy_loss": 0.0, "value_loss": 0.0, "entropy": 0.0}
        n_mb = 0
        for _ in range(cfg.epochs):
            order = self.rng.permutation(len(segments))
            for i in range(0, len(order), cfg.minibatch_segments):
                idx = order[i:i + cfg.minibatch_segments]
                mb = [segments[j] for j in idx]
                n = max(len(s.actions) for s in mb)

                def pad(xs, fill=0.0):
                    return torch.tensor(np.array([np.pad(np.asarray(x, dtype=np.float32), (0, n - len(x)),
                                                         constant_values=fill) for x in xs]))
                old_lp = pad([s.logps for s in mb])
                adv = (pad([gae[j][0] for j in idx]) - mean) / std
                ret = pad([gae[j][1] for j in idx])
                lp, v, ent, valid = self._replay(mb)
                w = valid.float()
                ratio = torch.exp(lp - old_lp)
                pl = -torch.min(ratio * adv, ratio.clamp(1 - cfg.clip, 1 + cfg.clip) * adv)
                policy_loss = (pl * w).sum() / w.sum()
                value_loss = (((v - ret) ** 2) * w).sum() / w.sum()
                entropy = (ent * w).sum() / w.sum()
                loss = policy_loss + cfg.value_coef * value_loss - cfg.entropy_coef * entropy
                self.optimizer.zero_grad()
                loss.backward()
                torch.nn.utils.clip_grad_norm_(self.policy.parameters(), cfg.max_grad_norm)
                self.optimizer.step()
                for k, x in (("loss", loss), ("policy_loss", policy_loss), ("value_loss", value_loss),
                             ("entropy", entropy)):
                    stats[k] += x.item()
                n_mb += 1
        self.iteration += 1
        return {k: v / max(n_mb, 1) for k, v in stats.items()}

    def train_step(self) -> dict[str, float]:
        """One PPO iteration: `games_per_iter` self-play games, then `epochs` passes over their segments; then the
        policy joins the past-snapshot pool every `past_checkpoints` iterations."""
        segs = []
        for _ in range(self.config.games_per_iter):
            segs += self.play_game(f"train-{self.iteration}-{self.games_played}")
        stats = self.update(segs)
        cfg = self.config
        if cfg.past_checkpoints and self.iteration % cfg.past_checkpoints == 0:
            snap = copy.deepcopy(self.policy).eval()
            snap.requires_grad_(False)
            self.past_pool = (self.past_pool + [snap])[-cfg.past_pool_size:]
        return stats

    # ---- checkpoints ----
    def save(self, path: str | Path) -> str:
        version = self.policy_version
        torch.save({
            "policy_version": version, "iteration": self.iteration, "games_played": self.games_played,
            "policy_config": asdict(self.policy.config), "train_config": asdict(self.config),
            "state_dict": self.policy.state_dict(), "optimizer": self.optimizer.state_dict(),
        }, path)
        return version


def load_checkpoint(path: str | Path | io.BytesIO) -> tuple[Policy, str, tuple[float, ...]]:
    """Policy, its `policy_version` and the raise fractions it was trained with (they fix the action indices)."""
    ckpt = torch.load(path, weights_only=False)
    policy = Policy(PolicyConfig(**ckpt["policy_config"]), seed=0)
    policy.load_state_dict(ckpt["state_dict"])
    fractions = tuple(ckpt["train_config"].get("raise_pot_fractions", DEFAULT_RAISE_FRACTIONS))
    return policy, ckpt["policy_version"], fractions


def load_policy(path: str | Path | io.BytesIO) -> tuple[Policy, str]:
    policy, version, _ = load_checkpoint(path)
    return policy, version


class PolicyAgent(Agent):
    """Plays a trained `Policy` through the director's Agent interface (evaluation, Gate L1).

    Opponent memory lives in a per-game `GameMemoryStore` and the GRU is reset in `on_game_start`, so nothing
    outlives a game. `action_probs` is pure (does not advance the GRU); `act` samples with the injected rng.
    """

    uses_memory = True

    def __init__(self, policy: Policy, config: TournamentConfig, rng: np.random.Generator,
                 raise_pot_fractions: tuple[float, ...] = DEFAULT_RAISE_FRACTIONS) -> None:
        self.policy, self.rng, self.fractions = policy, rng, tuple(raise_pot_fractions)
        self.builder = ObservationBuilder(config)
        self.memory = GameMemoryStore()
        self._state: torch.Tensor | None = None

    def on_game_start(self, game_id: str) -> None:
        self.memory.start_game(game_id)
        self._state = None

    def observe(self, event: Event) -> None:
        self.memory.observe(event)

    def on_game_end(self, game_id: str) -> None:
        self.memory.end_game(game_id)
        self._state = None

    @torch.no_grad()
    def _forward(self, observation: Observation):
        hero = self.builder.build(observation, self.memory.get(observation.game_id))
        mask = action_mask(hero, self.fractions)
        return hero, self.policy(self.policy.collate([hero]), torch.tensor([mask], dtype=torch.bool), self._state)

    def action_probs(self, observation: Observation) -> dict[str, float]:
        _, out = self._forward(observation)
        names = ["fold", "call"] + [f"raise_{f}" for f in self.fractions] + ["allin"]
        return {n: float(p) for n, p in zip(names, out.probs[0])}

    def act(self, observation: Observation) -> Action:
        hero, out = self._forward(observation)
        self._state = out.state
        probs = out.probs[0].double().numpy()
        return index_to_action(hero, int(self.rng.choice(len(probs), p=probs / probs.sum())), self.fractions)
