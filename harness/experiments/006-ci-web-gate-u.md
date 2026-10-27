# 006: CI web 잡 — Gate U(데모 E2E·3종 화면 스크린샷·axe)
- 상태: 진행 중
- 제안: planner, 2026-10-26 / 이슈 #99 / PR #124

## 문제 (관측 근거: journal·지표·리포트 인용)
웹 데모(`web/demo/`)가 회귀 검사 없이 바뀌고, Reviewer가 화면을 눈으로 볼 방법이 CI에 없다. 서비스 트랙(D1)의 판정 근거(스크린샷)가 로컬 실행뿐이다.
- 계획서 v1.1 §5 D1: Gate U(E2E + 3종 화면 스크린샷)를 CI 센서로 둔다.
- PR #124 리뷰: CI 아티팩트를 내려받지 못해 Reviewer가 로컬에서 같은 스크립트를 다시 돌려야 했다(참고용 수치).

## 가설
`web` 잡이 시작→훈련→채점→학습→복기 흐름을 Playwright로 통과시키고 화면마다 390×844·820×1180·1440×900 스크린샷을 아티팩트로 남기면, 데모 회귀를 CI가 잡고 Reviewer는 아티팩트만으로 화면을 판정할 수 있다. 스크린샷 3장이 같은 상태를 찍도록 진행을 멈추고 검사 대상 요소를 화면에 들이면 스크린샷이 검증한 요소를 실제로 보여준다.

## 변경
- `.github/workflows/ci.yml`: `web` 잡(Node 22, npm 캐시, Chromium 설치, `npm test`, 15분 제한, `if: always()` 아티팩트 `web-screenshots`).
- `web/e2e/gate-u.mjs`: E2E 흐름, 화면별 3종 스크린샷, 가로 스크롤·axe critical 검사. 찍는 동안 `window.__hold`로 데모 타이머를 미루고, 검사 요소(`focus`)를 화면에 들인 뒤 보이는지 assert한다.
- `web/demo/index.html`: 테스트 전용 `?speed`(기본 1). 기본 동작(1.5초 진행)은 그대로다. 진행 정지(`__hold`)는 스크립트가 init script로 주입하므로 데모는 건드리지 않는다.
- `tests/test_harness.py`: `web` 잡 구조 검사. 문서: `web/README.md`.

## 측정 지표와 측정창 (머지 후 14일)
1. 웹 관련 PR(`area:service`)에서 head sha의 `web` 잡이 success로 끝나는 비율과 소요 시간 중앙값.
2. 아티팩트 `web-screenshots`가 매 run에 15장 있는 비율.
3. Reviewer journal에서 "스크린샷을 로컬에서 재생성" 언급 횟수.

## 성공 기준 (수치)
- 지표 1: 소요 ≤ 5분, timeout 0회. 데모 회귀가 아닌 사유(러너·네트워크)로 실패한 run ≤ 10%.
- 지표 2 = 100%.
- 지표 3 = 0회.

## 롤백 방법
`ci.yml`의 `web` 잡 블록, `web/e2e/`, `tests/test_harness.py`의 `web` 잡 검사를 지우는 PR 하나(`harness-change`). 데모의 `?speed`는 기본 동작에 영향이 없어 남겨도 된다. 다른 잡은 영향을 받지 않는다.

## 결과 (측정창 종료 후 기록)
(미기록)
