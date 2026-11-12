# 037: CI numba 잡 — numba 경로 테스트를 `.[fast]`로 실제 실행, skip은 실패
- 상태: 진행 중
- 제안: builder, 2026-11-12 / 이슈 #786 / PR #794
## 문제 (관측 근거)
- CI `gates` 잡은 `.[dev]`만 설치해 numba 전용 테스트 2개(`test_e3_c1_cost.py::test_batch_kernel_equals_per_card_loop`, `test_e3_determinism.py::test_e3_fingerprint_is_identical_with_numba_disabled`)가 CI에서 늘 skip됐다(STATE friction (f), reviewer-b 11-02 보고, PR #776 「후속」 3).
- 학습 잡(`train.yml`)은 `.[fast]`로 numba 경로를 실제로 쓰므로, 쓰는 경로가 CI 무검증이었다.
## 가설
`gates` 시간을 늘리지 않는 짧은 전용 잡(`.[dev,fast]`, `pytest -m numba`, skip을 실패로 취급)을 두면 numba 경로 회귀가 PR 단계에서 보이고, 잡 비용은 1분 안팎에 그친다.
## 변경
- `pyproject.toml`: pytest 마커 `numba` 등록, 두 테스트에 `@pytest.mark.numba`.
- `tests/conftest.py`: `STALKER_REQUIRE_NUMBA=1`이면 numba 마커 테스트의 skip을 실패로 바꾼다.
- `.github/workflows/ci.yml`: 새 잡 `numba`(`timeout-minutes: 15`) — `import numba` 확인 → 마커 테스트가 있는 파일만 `pytest -m numba` → 출력에 `skipped`가 있거나 수집 0개면 실패. 필수 체크 아님. `gates-part`/`gates` 불변.
- `tests/test_harness.py`: 잡 timeout·extra 단언, conftest 훅 동작 테스트.
## 측정 지표와 측정창
머지 후 14일. 근거는 CI `numba` 잡 로그.
- `numba` 잡 실패 수와 원인 분류(numba 경로 회귀 / 설치·인프라 / skip 감지).
- `numba` 잡 시간(기준: PR #794 run 43155299329 42초, run 43162287876 40초).
- numba 경로 회귀를 이 잡이 먼저 잡은 사례 수(있으면 PR 번호).
## 성공 기준 (수치)
- 측정창 안 설치·인프라 원인 `numba` 잡 실패 ≤ 1건.
- `numba` 잡 시간 최댓값 < 5분.
- skip 0인 상태로 마커 테스트 2개 이상 실행(잡 로그 `passed` 수).
- 이 PR의 `numba` 잡 success(확인됨: run 43155299329, 43162287876).
## 롤백 방법
이 PR을 revert한다(`numba` 잡, `numba` 마커와 두 테스트의 데코레이터, conftest `STALKER_REQUIRE_NUMBA` 분기, 하네스 테스트 2개 제거). numba 테스트는 다시 CI에서 skip된다.
## 결과 (측정창 종료 후 기록)
