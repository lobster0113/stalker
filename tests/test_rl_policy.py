import dataclasses

import numpy as np
import pytest

from stalker.rl.env import TournamentEnv
from stalker.rl.features import SEAT_DIM, GLOBAL_DIM, encode, validate_observation
from test_rl_env import hyper_sng


def sample(n: int = 6, seed: int = 1):
    """First n (observation, mask) decisions of a random-play game."""
    env = TournamentEnv(hyper_sng())
    pol = np.random.default_rng(seed)
    res, out = env.reset(np.random.default_rng(seed)), []
    while len(out) < n and not res.done:
        out.append((res.observation, res.action_mask))
        res = env.step(int(pol.choice([i for i, m in enumerate(res.action_mask) if m])))
    env.close()
    return out


def test_features_shapes_and_variant_stats_mask():
    obs, _ = sample(8)[-1]
    f = encode(obs)
    assert f["seats"].shape == (9, SEAT_DIM) and f["glob"].shape == (GLOBAL_DIM,)
    assert f["seat_mask"].sum() == 6 and not f["seats"][~f["seat_mask"]].any()
    assert encode(obs, with_stats=False)["seats"][:, 7:].sum() == 0


def test_schema_rejects_fields_outside_contract():
    obs, _ = sample(1)[0]
    validate_observation(obs)
    with pytest.raises(ValueError, match="deck"):
        validate_observation(dataclasses.replace(obs, tournament={**obs.tournament, "deck": ("As",)}))
    with pytest.raises(ValueError, match="rng"):
        validate_observation(dataclasses.replace(obs, legal={**obs.legal, "rng": 1}))
    with pytest.raises(TypeError):
        validate_observation({"hole_cards": ("As", "Kd")})


torch = pytest.importorskip("torch")
from stalker.rl.policy import VARIANTS, Policy, PolicyConfig  # noqa: E402


def make(variant: str, seed: int = 0) -> Policy:
    return Policy(PolicyConfig(variant=variant, n_actions=5), seed)


@pytest.mark.parametrize("variant", VARIANTS)
def test_forward_shapes_and_illegal_actions_have_zero_probability(variant):
    pol, data = make(variant), sample(5)
    obs = [o for o, _ in data]
    mask = torch.tensor([m for _, m in data], dtype=torch.bool)
    mask[0] = torch.tensor([False, True, False, False, False])  # force a heavily masked row
    out = pol(pol.collate(obs), mask)
    assert out.probs.shape == (5, 5) and out.value.shape == (5,)
    assert (out.probs[~mask] == 0).all()
    assert torch.allclose(out.probs.sum(-1), torch.ones(5))
    assert (out.state is None) == (variant != "ai2")


def test_all_masked_row_is_an_error():
    pol, data = make("ai0"), sample(1)
    with pytest.raises(ValueError, match="legal action"):
        pol(pol.collate([data[0][0]]), torch.zeros(1, 5, dtype=torch.bool))


def test_ai1_differs_from_ai0_only_through_opponent_stats():
    obs, mask = sample(40)[-1]
    m = torch.tensor([mask])
    a0, a1 = make("ai0"), make("ai1")
    a1.load_state_dict(a0.state_dict())
    assert any(s.stats and s.hands_seen for s in obs.seats)
    assert not torch.allclose(a0(a0.collate([obs]), m).probs, a1(a1.collate([obs]), m).probs)
    no_stats = dataclasses.replace(obs, seats=tuple(dataclasses.replace(s, stats=None) for s in obs.seats))
    assert torch.equal(a0(a0.collate([no_stats]), m).probs, a1(a1.collate([no_stats]), m).probs)


def test_init_is_seeded_and_isolated_from_global_rng():
    torch.manual_seed(123)
    before = torch.get_rng_state()
    p1 = make("ai2", 5)
    assert torch.equal(torch.get_rng_state(), before)
    torch.rand(100)
    p2 = make("ai2", 5)
    assert all(torch.equal(v, p2.state_dict()[k]) for k, v in p1.state_dict().items())
    other = make("ai2", 6)
    assert not all(torch.equal(v, other.state_dict()[k]) for k, v in p1.state_dict().items())


@pytest.mark.parametrize("variant", VARIANTS)
def test_reset_memory_equals_fresh_policy(variant):
    pol, fresh, data = make(variant), make(variant), sample(6)
    for o, m in data[:4]:
        pol.act(o, m)
    pol.reset_memory()
    for o, m in data[4:]:
        assert torch.equal(pol.act(o, m).probs, fresh.act(o, m).probs)


def test_gru_state_carries_within_a_game():
    pol, data = make("ai2"), sample(3)
    (o1, m1), (o2, m2) = data[0], data[1]
    first = pol.act(o2, m2).probs
    pol.reset_memory()
    pol.act(o1, m1)
    assert not torch.equal(pol.act(o2, m2).probs, first)


def test_default_action_count_matches_env():
    assert PolicyConfig().n_actions == TournamentEnv(hyper_sng()).n_actions
