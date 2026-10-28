# ADR 0016: Gate S의 TP 변화 기준 — 눈금 한 칸 vs 고정 점수 폭

- 상태: 제안 → 이 PR 머지로 채택 (Builder 추천안으로 진행, `harness/PROTOCOL.md` §9)
- 이슈: #302 (선행 기록: #287, PR #286 리뷰 참고 2)

## 문제
Gate S 초기안은 "TP 변화 95백분위 ≤ 등급 눈금 한 칸"이다. 눈금 한 칸의 폭은 등급마다 다르다(초보 25점, 중수 10점, 고수 1점). 고수는 칸이 1점이라 기준이 사실상 "스택이 바뀌어도 값이 변하면 안 된다"가 된다. 분위 눈금 고수 정책은 스택이 같은 버킷 안에서 움직일 때 콜 레인지 대비 순위가 실제로 움직여 10칸(=10점) 변화로 실패한다(#287). 이 움직임은 앵커도 같은 방향으로 가는 정당한 반응일 수 있는데, 고운 눈금일수록 불리한 기준은 "고수에게 정밀한 TP를 주면 불합격"이라는 벌칙이다.

## 선택지
- **A. 현행: 등급 눈금 한 칸.** 단순. 고운 눈금일수록 엄격해져 등급 간 비교가 안 된다.
- **B. 고정 점수 폭 10점.** 등급과 무관한 같은 잣대. 초보(25점 칸)는 한 칸만 움직여도 실패 — 눈금 자체가 거칠어서 생기는 양자화 효과를 벌한다.
- **C. max(눈금 한 칸, 10점).** 거친 눈금은 한 칸 움직임을 허용(양자화), 고운 눈금은 10점까지 허용. 10점은 `docs/TP.md`의 채점 허용 오차(초보 ±12.5, 중수 ±5, 고수 ±3)와 같은 자릿수이며, 사람이 입력으로 구분하는 가장 거친 정밀도(중수 칸)다.

## 수치 (고정 시드, 1500회 CFR, **로컬 참고값** — `python -m referee.gate_s.threshold_table`)
"다른 기준"은 TV·안정화 regret·골든 통과(TP 변화 외)다.

| policy | TP 변화 p95 (칸 / 점) | 다른 기준 | A 한 칸 | B 10점 | C max |
|---|---|---|---|---|---|
| nash_anchor | - | ok | pass | pass | pass |
| oversensitive | - | fail (9) | fail | fail | fail |
| flat | - | fail (13) | fail | fail | fail |
| beginner quantile | 1 / 25 | fail (1: 골든 11/12) | fail | fail | fail |
| mid quantile | 1 / 10 | ok | pass | pass | pass |
| pro quantile | 10 / 10 | ok | fail | pass | pass |
| beginner uniform | 1 / 25 | fail (9) | fail | fail | fail |
| mid uniform | 1 / 10 | fail (9) | fail | fail | fail |
| pro uniform | 6 / 6 | ok | fail | pass | pass |

## 결정 (추천)
**C.** 판별력: 과민·평탄 정책은 TP 값이 없어 TV·골든으로만 판정되므로 세 기준 모두에서 실패하고 내시 앵커는 통과한다(TP 변화 항목은 이들에 영향이 없다). 점수 폭 항목 자체의 판별력은 `tests/test_gate_s.py`의 합성 정책(고운 눈금에서 6배 움직이면 실패)이 확인한다.

주의(솔직한 한계):
- 분위 눈금 고수의 p95는 정확히 10점으로 **경계값**이다. 이 통과는 큰 여유가 아니다. 1500회 로컬 값이며 기준은 CI 값으로 다시 본다.
- 기준을 실패한 후보를 본 뒤 바꾸는 것이므로(통계 절차 "기준 고정") 이전 결과를 위 표 A열에 남긴다. 이 변경으로 새로 통과하는 것은 고수 분위·균등 눈금 둘뿐이고, 둘 다 TV·regret·골든은 원래 통과였다. 초보·중수 결과는 바뀌지 않는다.
- 10점의 값은 TP.md 채점 허용 오차에서 가져온 것이지 최적화한 것이 아니다. 고수 눈금에 대한 요구를 더 올리려면 별도 ADR로 5점 등을 검토한다.

## 구현
- `spots_v1.json` `thresholds.tp_change_points = 10`(스팟·시드·골든은 그대로, sha256만 바뀜), `make_spots.py` 동기화.
- `evaluate`: 정책의 `tp_step_points`(없으면 눈금 전체=100점 → 한 칸 기준으로 되돌아감)로 칸→점 변환, 허용 = max(`tp_change_steps` × 칸 폭, `tp_change_points`). 결과에 `tp_change_p95_points` 추가.
- `gate_s_policy`가 등급별 칸 폭(`TIER_STEP`)을 단다. CI 지표 `gate_s_e1`에 `tp_change_p95_points` 추가(`tp_change_p95`는 칸 단위 유지).
