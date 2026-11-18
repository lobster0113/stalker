# ADR 0028: 빠진 북극성 축 재산출 경로 — Gate T 통과율·처리량부터

- 상태: 제안. 이 PR이 머지되면 채택한다(Builder 추천안으로 진행, `harness/PROTOCOL.md` §9).
- 이슈: #892. 현황표: `docs/research/2026-11-north-star-coverage.md`. 관련: ADR 0008(Gate A/B 은퇴), #683(`e3_web_lbr` 등록 선례).
- 직접 돌린 수치는 없다. 비용은 가정이다.

## 맥락
Auditor가 W44~W46에 "북극성 Gate A/B/C 미산출"을 반복 지적했다. 현황표 결과: A/B는 은퇴, C는 없는 이름이고, 현행 축 중 history에 없는 것은 Gate T·처리량·Q1·Q2·복잡성 비용·3인 이상 최대 손실·U·E·하네스다. 이 중 평가기가 이미 있어 등록만 하면 되는 것은 Gate T와 처리량이다.

## 결정
1. **`gate_t_pass_rate`·`gate_t_checks`를 먼저 등록한다.** `referee/metrics.py`에 `gate_t()` 부분을 추가하고 `snapshot()`의 부분 목록에 넣는다. REGISTRY의 모든 정책에 T1~T4를 돌려 통과/전체를 합산한다(`referee/gate_t/__init__.py`의 `main()`과 같은 호출). 시간 상한: 부분당 120초(현재 `gates full`에서 이미 도는 검사라 추가 분은 가정상 1분 안팎). 목표 값은 1.0(TP 준수 = 100%).
2. **`sim_hands_per_sec`을 둘째로 등록한다.** `stalker/tools/bench_engine.py`의 고정 시드 짧은 측정(상한 60초)을 `metrics.py` 부분으로 감싼다. 러너 편차가 크므로 판정에 쓰지 않고 4주 기울기용 보고 지표로만 둔다(이동 중앙값 사용은 Auditor 몫).
3. 나머지(Q1·Q2·복잡성 비용·3인 이상 최대 손실)는 클라우드 결과를 history로 복사하는 경로(`e3_web_lbr` 방식)가 필요해 지금 정하지 않는다. Gate U·하네스 축은 history 밖(CI 아티팩트·Auditor 리포트)에서 보기로 한다.
4. Auditor 리포트의 "Gate A/B/C"는 현황표 §2대로 읽는다.

## 대안
- 전 축을 한 번에 등록: 평가기가 없는 축(복잡성 비용·E)이 있어 불가능하다.
- Gate U 요약을 history에 넣기: 가치는 있으나 `ci.yml` 수정(하네스 경로)이 필요해 별도 이슈로 둔다.

## 결과·후속
구현은 `referee-change` 이슈(보호 경로 `referee/metrics.py`)로 따로 올린다. 초안은 PR 본문 "후속".
