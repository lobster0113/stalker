# 002: CI rl 잡 — torch 테스트를 CI에서 실제로 실행
- 상태: 진행 중
- 제안: planner, 2026-10-24 / 이슈 #51 / PR #54

## 문제 (관측 근거: journal·지표·리포트 인용)
`gates` 잡은 `[dev]`만 설치하므로 torch 테스트(`tests/test_rl_*.py`)가 CI에서 모두 skip된다. RL 수용 기준의 근거가 로컬 실행뿐이다.
- journal 2026-10-24T10:30 builder-b (#42/PR #48): "CI likely lacks [rl] so tests skip"
- journal 2026-10-24T14:10 reviewer (PR #48): "CI installs only [dev], so all policy tests skip in CI and acceptance criteria 1-3 have no CI evidence; reviewer had to install torch locally (~10 min ...)"
- journal 2026-10-24T15:13 reviewer (PR #48): "수용 기준 근거가 로컬뿐. 로컬 torch 설치에 10분+ 소요"
- STATE.md 10-24: #43이 CI 근거 확보(#51)를 기다리며 blocked.

## 가설
독립 `rl` 잡(CPU torch, `[dev,rl]`)이 RL 테스트를 돌리고, `STALKER_REQUIRE_TORCH=1`일 때 torch skip을 실패로 바꾸면, RL PR의 수용 기준을 CI 결과만으로 판정할 수 있다. 그러면 Reviewer·Builder가 로컬에 torch를 설치하는 시간이 없어진다.

## 변경
- `.github/workflows/ci.yml`: `rl` 잡 추가(Python 3.12, pip 캐시, CPU torch 인덱스, `pytest -rs tests/test_rl_*.py`, 20분 제한). 기존 잡은 그대로 둔다.
- `tests/conftest.py`: `STALKER_REQUIRE_TORCH=1`이면 사유에 torch가 들어간 skip을 실패로 바꾼다.
- `tests/test_harness.py`: 훅 동작과 ci.yml 구조를 검사하는 테스트 3개.

## 측정 지표와 측정창 (머지 후 14일)
1. RL 관련 PR(`area:ai` 중 torch 테스트를 바꾼 PR)에서 head sha의 `rl` 잡이 success로 끝나고 SKIPPED가 0건인 비율.
2. journal friction에서 "torch 테스트가 CI에서 skip"이나 "로컬 torch 설치" 언급 횟수.
3. `rl` 잡 소요 시간 중앙값(PR #54 기준 44s, pip 캐시 적중).

## 성공 기준 (수치)
- 지표 1 ≥ 90%(해당 PR이 1개 이상 있을 때).
- 지표 2 = 0회(Reviewer·Builder 모두).
- 지표 3 ≤ 5분, `rl` 잡 timeout(20분) 발생 0회.

## 롤백 방법
`ci.yml`의 `rl` 잡 블록과 `tests/conftest.py`의 `STALKER_REQUIRE_TORCH` 훅, `tests/test_harness.py`의 관련 테스트 3개를 지우는 PR 하나(`harness-change`). 다른 잡과 코드는 영향을 받지 않는다.

## 결과 (측정창 종료 후 기록)
(미기록)
