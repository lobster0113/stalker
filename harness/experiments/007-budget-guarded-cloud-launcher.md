# 007: 예산 가드 클라우드 런처 (RunPod, CI 전용)
- 상태: 진행 중
- 제안: planner, 2026-10-23 / 이슈 #20 / PR (이 PR)

## 문제 (관측 근거: journal·지표·리포트 인용)
D3 학습 단계와 처리량 파일럿에는 클라우드 연산이 필요한데, 사람 개입 없이 돈을 쓰는 경로가 없다(ADR 0004 §5).
사용자가 NH-1을 결정했다(#20 코멘트 2026-10-27: 월 상한 $100, 선불 크레딧 $100·자동 충전 꺼짐, Secret `RUNPOD_API_KEY` 등록).
에이전트가 키를 보지 않고, 상한을 넘을 수 없고, 인스턴스가 남지 않는 구조가 필요하다.

## 가설
돈을 쓰는 유일한 경로를 CI 워크플로 하나(`cloud.yml`)로 좁히고, 실행 전 원장 검사(진행분은 최악 비용으로 예약)·단가 상한·최대 시간·finally 종료·일 1회 고아 감시를 겹치면,
에이전트가 작업 명세 PR만으로 연산을 쓰면서도 월 지출이 `harness/budget.json` 상한을 넘지 않고 고아 pod가 24시간 넘게 남지 않는다.

## 변경
- `harness/cloud/launcher.py`: `check`·`run [--dry-run]`·`reap [--force]`. 표준 라이브러리만(RunPod REST `rest.runpod.io/v1`, 잔액은 GraphQL).
- `.github/workflows/cloud.yml`: dispatch(mode/job/dry_run) + cron `17 3 * * *`(reap). `concurrency: cloud-budget`(취소 없음)로 원장 경쟁 차단. `if: always()` 정리(이 run의 pod 강제 종료)·원장 ops push. Secret은 `RUNPOD_API_KEY`만.
- `harness/budget.json` `{"monthly_cap_usd": 100}`, `jobs/README.md`·`jobs/smoke-cpu.yaml`(최악 $0.02), reviewer.md 11항(상한 인상 CLOSE), PROTOCOL §1 원장 행.
- `tests/test_cloud_launcher.py`: mock API로 예산 거부·완료·시간 초과·오류·단가 초과·reap·상한 고정·워크플로 가드.

## 측정 지표와 측정창 (머지 후 30일)
1. 머지 후 첫 `mode=check` run이 success(키 유효). 실패면 NEEDS_HUMAN에 키 재등록 요청.
2. `jobs/smoke-cpu.yaml` dry run → 실제 run이 success, 원장에 start/end 각 1줄, `actual_usd` ≤ $0.02.
3. 월별 원장 합계 ≤ 상한(RunPod 대시보드 지출과 ±10% 이내 — Auditor 주간 리포트에서 대조).
4. reap run이 매일 success, 기한 지난 `stalker-*` pod 0.

## 성공 기준 (수치)
- 지표 1·2: 첫 시도에서 충족(API 필드 불일치로 실패 시 수정 PR 1회까지 허용).
- 지표 3: 상한 초과 0회, 원장-대시보드 차이 ≤10%.
- 지표 4: 고아 pod 수명 ≤ 24시간 + max_minutes.

## 롤백 방법
`.github/workflows/cloud.yml`을 지우는 PR 하나(`harness-change`)로 돈 쓰는 경로가 사라진다. 급하면 `harness/budget.json`을 `{"monthly_cap_usd": 0}`으로 내리는 PR(낮추는 방향은 허용)로 모든 run이 거부된다. 남은 pod는 RunPod 콘솔에서 사람이 종료(NEEDS_HUMAN).

## 결과 (측정창 종료 후 기록)
(미기록)
