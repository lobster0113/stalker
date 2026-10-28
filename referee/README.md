# referee/ — 심판 (보호 경로)

STALKER의 모든 "좋아졌다/나빠졌다" 판정은 여기의 코드가 CI에서 계산한다. 선수(Builder)는 심판을 고칠 수 없다.
수정은 `referee-change` 라벨이 붙은 이슈에서만, Reviewer의 심판 변경 추가 검토(`harness/routines/reviewer.md` §1-5)를 거쳐서만 가능하다.

| 파일 | 역할 |
|---|---|
| `PROTECTED_PATHS` | 라벨별 보호 경로 |
| `guard.py` | PR이 보호 경로를 라벨 없이 바꾸면 CI 실패 |
| `gates.py` | G0/G1/G2 게이트 (`quick`, `full`) |
| `anchors/` | 이론 기준선: ICMizer-등가 참조기(`icm_reference.py`), HU 클래스 에퀴티 테이블(`hu_equity.py`), HU 푸시/폴드 내시·EV 손실(`pushfold.py`) |
| `stats.py` | 게이트 통계: 클러스터 부트스트랩 CI, SPRT(무익성 중단 전용), 비열등성/우월성 판정, 필요 표본 수 |
| `evaluate.py` | duplicate 토너먼트 평가: 후보 vs 기준 에이전트 ROI 차이와 CI, 결과 JSON(설정·시드 정책·참조기 버전) |
| `gate_l.py` | Gate L 정보 누출·기억 경계: L1/L2/L5는 임의 `Agent` 팩토리를, L3/L4/L5는 관측·메모리 파이프라인을 검사. `python -m referee.gate_l`. 새 정책은 `REGISTRY`에 등록 |
| `gate_r/` | Gate R 규칙 정확성 스위트: 독립 평가기·사이드팟 정산·이벤트 재생 검사, `python -m referee.gate_r`; 엣지 케이스 8종 `python -m referee.gate_r.edge` (`GATES.md` Gate R) |
| `metrics.py` | main 머지마다 `ops:metrics/history.jsonl`에 append되는 지표 스냅샷 |

## 게이트 통계 (`stats.py`, `evaluate.py`)
- **duplicate 블록 = 부트스트랩 클러스터.** 블록 하나는 같은 게임 시드로 A/B 마스크(연속 블록: player_id 0..⌈n/2⌉−1 = 후보)와 그 보완 마스크(전 좌석 교환)를 `rotations`개 순환 이동마다 플레이한다. 이동마다 새 마스크 쌍이 나오도록 `rotations` ≤ n/2(n 짝수, 예: 6max ≤ 3)·≤ n(n 홀수)로 제한하고, 넘으면 `ValueError`. 블록 diff = 블록 내 게임들의 (후보 평균 ROI − 기준 평균 ROI) 평균. ROI 비용 = 상금풀/인원.
- 판정: `superiority` = 95% CI 하한 > 0 그리고 ≥ δ_min, `noninferiority` = 하한 > −δ_ni. 양측 95% CI의 하한을 읽으므로 단측 유의수준은 2.5%다(합성 데이터 1종 오류 실측 ≈ 0.026, `tests/test_gate_stats.py`).
- `sprt`는 **무익성 중단 전용**이다(GATES 표본 정책). `accept_h0`이면 멈춰 실패로 보고할 수 있지만, `accept_h1`은 성공 근거가 아니다 — 성공은 사전 등록한 블록 수를 채운 뒤 CI로만 판정한다.

### 필요 표본 수 계산기
`required_tournaments(sigma, delta, alpha=0.05, power=0.9)` = ⌈((z₀.₉₇₅ + z₀.₉)·σ/δ)²⌉ = ⌈10.51·(σ/δ)²⌉ **블록**. σ는 실제로 돌릴 duplicate 방식(같은 `rotations`)으로 잰 블록 diff의 표준편차다.

무작위 봇 A/A로 잰 추정치 (로컬, 참고용 — 2026-10-24, 블록 300개·rotations=1·연속 블록 마스크, 비교용 독립 게임 600개):

| 프리셋 | 블록(2게임) diff SD | 독립 2게임 평균 SD | duplicate 분산 비 | δ=0.05 | δ=0.10 | δ=0.20 (ROI) |
|---|---|---|---|---|---|---|
| 6max_sng_wta | 1.278 | 1.415 | 0.82 | 6860 블록 | 1715 | 429 |
| 9max_sng_503020 | 0.656 | 0.774 | 0.72 | 1812 | 453 | 114 |

- 블록 수 × 2 = 게임 수. 무작위 봇 게임은 4핸드 안팎으로 끝나 실제 에이전트보다 분산 구조가 다르다. 게이트별 사전 등록 표본은 **해당 후보·기준 쌍으로 σ를 다시 재서** 정한다(GATES: duplicate 분산 감소는 실측한 뒤에만 반영).
- 재현: 블록 diff는 `evaluate(cfg, f, f, blocks=300, seed=100).block_diffs`(rotations=1, 연속 블록 마스크)의 표본 SD. 마스크를 교대→연속 블록으로 바꾼 뒤 다시 쟀다(2026-10-24, 로컬). 독립 게임 열은 마스크와 무관해 그대로다.

## 앞으로 추가될 것 (Planner가 `referee-change` 이슈로 관리)
- 재현성 체크(G1)
- 벤치마크 봇 필드 + G2 등록 (평가기·신뢰구간은 `evaluate.py`·`stats.py`로 구현됨)
- 적응 가치 평가: 적응형 vs 사전정보 고정 AI (G2)
- 이론 앵커: 숏스택 push/fold 내시 대비 EV 손실 (G2)
- 챔피언 리그·승급 (main 머지 후)
- 홀드아웃 평가: `HOLDOUT_SEED` GitHub Secret 사용, 일 1회 (에이전트는 시드를 볼 수 없다)
- 유형화 지표: 커버리지·안정성·증류 충실도
