"""Regenerate t4_spots_v1.json: python -m referee.gate_t.make_t4_spots (changing the set changes its sha256)."""
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


FLOP_HU = dict(board="Kc7d2s", history=[[3, "cbr", 2.5], [0, "cc", 2.5], [0, "cc", 0], [3, "cbr", 3]], bets_bb={"3": 3}, pot_bb=8)
pairs = [
    ("heads_up_vs_multiway", "두 명 남은 팟과 셋이 남은 팟은 필요한 핸드 강도가 다르다",
     v(), v(in_hand=[0, 3, 4], bets_bb={"3": 2.5, "4": 2.5}, history=BASE["history"][:4] + [[4, "cc", 2.5], [5, "f", 0]], pot_bb=6.5)),
    ("bubble_vs_in_the_money", "버블 직전의 콜은 머니인 확정 뒤보다 칩 손실이 무겁다",
     v(players_remaining=3, paid_places=2, button=4, stacks_bb={"0": 30, "3": 27.5, "4": 30}, in_hand=[0, 3],
       history=[[3, "cbr", 2.5], [4, "f", 0]]),
     v(players_remaining=2, paid_places=2, button=3, stacks_bb={"0": 30, "3": 27.5}, in_hand=[0, 3],
       history=[[3, "cbr", 2.5]])),
    ("button_vs_early_position", "같은 핸드도 포지션에 따라 오픈·디펜스 범위가 다르다",
     v(button=0), v(button=3)),
    ("short_vs_deep_stack", "8BB는 올인/폴드 영역, 40BB는 포스트플랍을 고려한다",
     v(stacks_bb=stacks(s0=8)), v(stacks_bb=stacks(s0=40))),
    ("small_raise_vs_all_in", "작은 레이즈와 올인에 대한 대응은 다르다",
     v(), v(bets_bb={"3": 30}, stacks_bb=stacks(s3=0))),
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
     v(stacks_bb=stacks(s3=0), bets_bb={"3": 30}), v(stacks_bb=stacks(s3=27.5), bets_bb={"3": 30})),
    ("strong_vs_weak_hand", "같은 상황에서 AK와 72o는 다르게 둔다",
     v(hole="AhKd"), v(hole="7c2d")),
    ("three_vs_four_way", "인원 버킷(3인 vs 4인+)이 다르다",
     v(in_hand=[0, 3, 4], bets_bb={"3": 2.5, "4": 2.5}, pot_bb=6.5),
     v(in_hand=[0, 3, 4, 5], bets_bb={"3": 2.5, "4": 2.5, "5": 2.5}, pot_bb=9.0)),
    ("final_table_vs_early", "파이널 테이블과 초반은 상금 압박이 다르다",
     v(players_remaining=6, paid_places=2), v(players_remaining=40, paid_places=6)),
    ("winner_take_all_vs_flat", "승자독식과 플랫 페이아웃은 생존 가치가 다르다",
     v(preset="6max_sng_wta"), v(preset="9max_sng_flat")),
    ("check_option_vs_facing_bet", "체크할 수 있을 때와 벳을 마주했을 때는 다르다",
     v(**{**FLOP_HU, "bets_bb": {}, "history": FLOP_HU["history"][:3]}), v(**FLOP_HU)),
    ("hero_vs_villain_preflop_aggressor", "누가 프리플랍 공격자인가에 따라 레인지가 다르다",
     v(history=[[1, "f", 0], [2, "f", 0], [3, "cbr", 2.5], [4, "f", 0], [5, "f", 0]]),
     v(history=[[1, "f", 0], [2, "f", 0], [3, "cbr", 2.5], [4, "f", 0], [5, "f", 0], [0, "cbr", 8], [3, "cbr", 20]],
       bets_bb={"0": 8, "3": 20}, pot_bb=29)),
    ("deep_vs_short_opponent", "상대 스택이 짧으면 유효 스택이 줄어든다",
     v(stacks_bb=stacks(s3=4)), v(stacks_bb=stacks(s3=50))),
    ("small_blind_vs_big_blind", "헤즈업 프리플랍에서 SB와 BB는 행동 순서와 범위가 다르다",
     v(button=5), v(button=4)),
]
out = {"version": 1, "pairs": [{"id": i, "why": w, "a": a, "b": b} for i, w, a, b in pairs]}
(Path(__file__).resolve().parent / "t4_spots_v1.json").write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
print(len(pairs))
