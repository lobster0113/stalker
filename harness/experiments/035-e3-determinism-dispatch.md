# 035: E3 결정성 비교 workflow_dispatch 잡
- 상태: 진행 중
- 제안: builder-b, 2026-11-10 / 이슈 #463 / PR #725

## 문제 (관측 근거: journal·지표·리포트 인용)
같은 시드 2×10⁴ iter를 서로 다른 수치 설정에서 돌려 regret 해시를 비교하는 일(#447, PR #456 리뷰 item 3(b))이 로컬에서 9분 안에 끝나지 않아 근거 수치를 낼 곳이 없다. 성능·결정성 근거는 CI뿐이다.

## 가설
수동 실행 전용 잡이 `stalker.tools.e3_determinism`을 돌려 JSON을 아티팩트로 남기면, 로컬 실행 없이 CI 수치로 설정 간 일치 여부를 확인할 수 있다. PR·push 트리거가 없어 필수 체크와 CI 시간에 영향이 없다.

## 변경
- `.github/workflows/e3-determinism.yml`: `workflow_dispatch`(입력 `iters`, 기본 20000), 120분 제한, `permissions: contents: read`, 입력은 env(`ITERS`)로 전달, `upload-artifact`(`if: always()`).
- `docs/ARCHITECTURE.md` CI 절에 한 문장.

## 측정 지표와 측정창 (머지 후 14일)
1. 머지 후 첫 dispatch run의 완료 여부와 소요 시간.
2. 아티팩트 JSON의 설정별 `equal` 값.

## 성공 기준 (수치)
- 첫 기본 입력 run이 120분 timeout 안에 success로 끝난다.
- 모든 설정 `equal: true`(false면 잡이 실패하고, 그 자체가 결정성 결함 보고).

## 롤백 방법
`.github/workflows/e3-determinism.yml`을 지우는 PR 하나(`harness-change`). 필수 체크가 아니므로 다른 잡에 영향 없음.

## 결과 (측정창 종료 후 기록)
(미기록)
