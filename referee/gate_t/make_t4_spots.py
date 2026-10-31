"""Regenerate t4_spots_v1.json: python -m referee.gate_t.make_t4_spots (changing the set changes its sha256).

Spots leave the blinds out of `bets_bb` (both sides of a pair alike), so SB/BB pairs differ in position, not price.
"""
import copy
import json
from pathlib import Path

BASE = {
    "preset": "6max_sng_wta", "hero_seat": 0, "button": 5,
    "stacks_bb": {"0": 30, "1": 30, "2": 30, "3": 27.5, "4": 30, "5": 30},
    "in_hand": [0, 3], "bets_bb": {"3": 2.5}, "pot_bb": 4.0, "hole": "AhKd", "board": "",
    "history": [[1, "f", 0], [2, "f", 0], [3, "cbr", 2.5], [4, "f", 0], [5, "f", 0]],
    "players_remaining": 6, "paid_places": 2,
}


def v(**kw):
    s = copy.deepcopy(BASE)
    for k, x in kw.items():
        s[k] = x
    return s


def stacks(**kw):
    s = dict(BASE["stacks_bb"])
    s.update({k[1:]: x for k, x in kw.items()})
    return s


# Seat 3 raises to 30BB instead of 2.5BB; the history amount must match bets_bb (#254).
SHOVE_30 = [[1, "f", 0], [2, "f", 0], [3, "cbr", 30], [4, "f", 0], [5, "f", 0]]
FLOP_HU = dict(board="Kc7d2s", history=[[3, "cbr", 2.5], [0, "cc", 2.5], [0, "cc", 0], [3, "cbr", 3]], bets_bb={"3": 3}, pot_bb=8)
pairs = [
    ("heads_up_vs_multiway", "두 명 남은 팟과 셋이 남은 팟은 필요한 핸드 강도가 다르다",
     # Same pot, price and stacks; only the number of opponents in the hand changes (#248 review). Side a
     # carries 2.5BB of dead chips so its pot equals side b's (where seat 4 called the 2.5BB open).
     v(pot_bb=6.5),
     v(in_hand=[0, 3, 4], bets_bb={"3": 2.5, "4": 2.5}, pot_bb=6.5,
       history=[[1, "f", 0], [2, "f", 0], [3, "cbr", 2.5], [4, "cc", 2.5], [5, "f", 0]])),
    ("bubble_vs_in_the_money", "버블 직전의 콜은 머니인 확정 뒤보다 칩 손실이 무겁다",
     # The same table; only the field changes: 7 left with 6 paid (bubble) vs 6 left (in the money).
     v(players_remaining=7, paid_places=6), v(players_remaining=6, paid_places=6)),
    ("button_vs_early_position", "같은 핸드도 포지션에 따라 오픈·디펜스 범위가 다르다",
     v(button=0), v(button=3)),
    ("short_vs_deep_stack", "8BB는 올인/폴드 영역, 40BB는 포스트플랍을 고려한다",
     v(stacks_bb=stacks(s0=8)), v(stacks_bb=stacks(s0=40))),
    ("small_raise_vs_all_in", "작은 레이즈와 올인에 대한 대응은 다르다",
     v(), v(bets_bb={"3": 30}, stacks_bb=stacks(s3=0), history=SHOVE_30)),
    ("preflop_vs_flop", "보드가 깔리면 판단 재료가 바뀐다",
     v(), v(**FLOP_HU)),
    ("call_leaves_under_one_bb", "콜하면 1BB도 안 남는 스택은 사실상 올인 결정이다",
     v(stacks_bb=stacks(s0=3)), v(stacks_bb=stacks(s0=12))),
    ("raise_legal_vs_not", "레이즈할 수 없으면 선택지가 줄어든다",
     v(), v(can_raise=False)),
    ("cheap_vs_expensive_call", "같은 콜도 팟이 크면 필요한 승률이 낮다",
     v(pot_bb=4.0), v(pot_bb=20.0)),
    ("chip_leader_vs_short_rank", "칩 순위가 다르면 ICM 압박이 다르다",
     v(all_stacks_bb=[30, 10, 10, 10, 10, 10]), v(all_stacks_bb=[60, 60, 60, 60, 60, 30])),
    ("paired_vs_unpaired_board", "페어 보드는 레인지 강도 분포를 바꾼다",
     v(**FLOP_HU), v(**{**FLOP_HU, "board": "KcKd2s"})),
    ("turn_vs_river", "리버에는 다음 카드가 없다",
     v(**{**FLOP_HU, "board": "Kc7d2s9h"}), v(**{**FLOP_HU, "board": "Kc7d2s9h3c"})),
    ("opponent_all_in_vs_not", "상대가 올인이면 이후 베팅이 없다",
     v(stacks_bb=stacks(s3=0), bets_bb={"3": 30}, history=SHOVE_30),
     v(stacks_bb=stacks(s3=27.5), bets_bb={"3": 30}, history=SHOVE_30)),
    ("strong_vs_weak_hand", "같은 상황에서 AK와 72o는 다르게 둔다",
     v(hole="AhKd"), v(hole="7c2d")),
    ("three_vs_four_way", "인원 버킷(3인 vs 4인+)이 다르다",
     # Same pot and price; side a carries 2.5BB of dead chips to match side b's extra caller.
     v(in_hand=[0, 3, 4], bets_bb={"3": 2.5, "4": 2.5}, pot_bb=9.0,
       history=[[1, "f", 0], [2, "f", 0], [3, "cbr", 2.5], [4, "cc", 2.5], [5, "f", 0]]),
     v(in_hand=[0, 3, 4, 5], bets_bb={"3": 2.5, "4": 2.5, "5": 2.5}, pot_bb=9.0,
       history=[[1, "f", 0], [2, "f", 0], [3, "cbr", 2.5], [4, "cc", 2.5], [5, "cc", 2.5]])),
    ("final_table_vs_early", "파이널 테이블과 초반은 상금 압박이 다르다",
     v(players_remaining=6, paid_places=2), v(players_remaining=40, paid_places=6)),
    ("winner_take_all_vs_flat", "승자독식과 플랫 페이아웃은 생존 가치가 다르다",
     v(preset="6max_sng_wta"), v(preset="9max_sng_flat")),
    ("check_option_vs_facing_bet", "체크할 수 있을 때와 벳을 마주했을 때는 다르다",
     v(**{**FLOP_HU, "bets_bb": {}, "history": FLOP_HU["history"][:3]}), v(**FLOP_HU)),
    ("early_vs_button_opener", "앞 포지션 오픈과 버튼 오픈은 오픈 레인지가 달라 같은 핸드도 다르게 막는다",
     # Same price and stacks; only the opener's seat (aggressor position) changes. "Hero vs villain as preflop
     # aggressor" needs postflop street markers in the DecisionContext (preflop the hero cannot be the last
     # aggressor and still act), so it waits for that (#248 review).
     v(), v(bets_bb={"5": 2.5}, stacks_bb=stacks(s3=30, s5=27.5), in_hand=[0, 5],
            history=[[1, "f", 0], [2, "f", 0], [3, "f", 0], [4, "f", 0], [5, "cbr", 2.5]])),
    ("deep_vs_short_opponent", "상대 스택이 짧으면 유효 스택이 줄어든다",
     v(stacks_bb=stacks(s3=4)), v(stacks_bb=stacks(s3=50))),
    ("small_blind_vs_big_blind", "헤즈업 프리플랍에서 SB와 BB는 행동 순서와 범위가 다르다",
     v(button=5), v(button=4)),
]

# DecisionContext fields each pair is expected to change: the named fact plus what follows from it by the
# rules (an all-in also changes the price and the legal actions). tests/test_gate_t4.py checks the actual
# difference is exactly this, so a confound (e.g. pot size riding along with the opponent count) shows up.
DIFFERS = {
    "heads_up_vs_multiway": ["opponents_to_act", "opponent_positions"],
    "bubble_vs_in_the_money": ["tournament_public_summary"],
    "button_vs_early_position": ["hero_position", "position_vs_button", "opponent_positions", "street_aggressor",
                                 "preflop_aggressor"],
    "short_vs_deep_stack": ["max_raise", "effective_stack_bb", "spr", "tournament_public_summary"],
    "small_raise_vs_all_in": ["opponents_to_act", "opponent_positions", "legal_actions", "to_call", "min_raise",
                              "max_raise", "required_equity", "all_in", "tournament_public_summary"],
    "preflop_vs_flop": ["street", "street_aggressor", "preflop_aggressor", "to_call", "min_raise", "pot", "spr",
                        "required_equity", "board"],
    "call_leaves_under_one_bb": ["min_raise", "max_raise", "effective_stack_bb", "spr", "tournament_public_summary"],
    "raise_legal_vs_not": ["legal_actions", "min_raise", "max_raise"],
    "cheap_vs_expensive_call": ["pot", "spr", "required_equity"],
    "chip_leader_vs_short_rank": ["tournament_public_summary"],
    "paired_vs_unpaired_board": ["board"],
    "turn_vs_river": ["street", "board"],
    "opponent_all_in_vs_not": ["opponents_to_act", "opponent_positions", "all_in", "tournament_public_summary"],
    "strong_vs_weak_hand": ["hole_cards"],
    "three_vs_four_way": ["opponents_to_act", "opponent_positions"],
    "final_table_vs_early": ["tournament_public_summary"],
    "winner_take_all_vs_flat": ["tournament_public_summary"],
    "check_option_vs_facing_bet": ["legal_actions", "to_call", "min_raise", "effective_stack_bb", "spr", "required_equity"],
    "early_vs_button_opener": ["opponent_positions", "street_aggressor", "preflop_aggressor"],
    "deep_vs_short_opponent": ["effective_stack_bb", "spr", "tournament_public_summary"],
    "small_blind_vs_big_blind": ["position_vs_button", "opponent_positions", "street_aggressor", "preflop_aggressor"],
}
out = {"version": 1, "pairs": [{"id": i, "why": w, "differs": DIFFERS[i], "a": a, "b": b} for i, w, a, b in pairs]}
# LF on every OS: the loader hashes the raw bytes.
(Path(__file__).resolve().parent / "t4_spots_v1.json").write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n",
                                                                  encoding="utf-8", newline="\n")
print(len(pairs))
