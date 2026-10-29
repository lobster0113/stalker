# 025: 클라우드 파드 병렬 실행 — 잡별 concurrency, 원장 union 병합, 예약 후 재검사
- 상태: 진행 중
- 제안: 대화 세션, 2026-10-29 / 이슈 #350
## 문제 (관측 근거)
`cloud.yml`은 모든 실행을 `concurrency: cloud-budget` 하나로 직렬화한다. GitHub concurrency는 같은 그룹에 대기 실행을 하나만 둔다. 2026-10-29에 고수 파드 학습(cloud run 40840669062, 최대 320분)을 실행했고, 그 사이 중수 6인 파드(40846037897)는 대기열에 있다. 이때 중수 9인을 넣으면 대기 중인 중수 6인이 취소된다. 그래서 파드 학습 일정(ADR 0017, 사용자 지시 "학습 속도 우선")이 파드 개수만큼 직렬로 늘어진다.
## 가설
잡이 다르면 같은 원장을 동시에 써도 다음 두 장치로 월 상한을 지킬 수 있다.
1. 원장 append를 union 병합한다.
2. 예약을 동기화한 뒤 월 합계를 다시 확인한다.

두 실행이 동시에 예산 검사를 통과해도 늦게 push한 쪽은 pull로 먼저 push한 쪽의 예약을 받고, 먼저 push한 쪽은 늦은 쪽이 자기 예약을 보게 된다. 그래서 둘 중 적어도 하나가 상한 초과를 발견하고 파드를 바로 종료한다. 초과 비용은 파드 생성부터 종료까지 몇 초에서 몇 분이다.
## 변경
- `.github/workflows/cloud.yml`: run은 `cloud-run-<job>` 그룹으로 보낸다(같은 잡은 직렬). check·reap·collect·schedule은 `cloud-budget`에 남긴다.
- `harness/cloud/push_ledger.sh`: git common dir의 `info/attributes`에 `budget/ledger.jsonl merge=union`을 둔다. 커밋하지 않는다. 동시 append가 rebase에서 둘 다 남는다.
- `harness/cloud/launcher.py`: `run_job`이 sync 뒤에 원장을 다시 읽어 월 합계가 상한을 넘으면 `BudgetExceeded`를 내고 status `over_cap`으로 기록한다. 파드는 finally에서 종료된다.
- 테스트: 병렬 예약으로 상한을 넘으면 폴링 전에 종료하고 `over_cap`으로 기록하는지 본다. 실제 git과 bash로 두 클론이 같은 줄 끝에 append한 뒤 push했을 때 세 줄이 모두 남는지도 본다.
## 알려진 한계
- 일일 reap(03:17Z, `cloud-budget`)은 ops를 읽은 뒤 파드 목록을 본다. 그 사이 몇 초 안에 다른 잡이 만든 파드는 원장에 없어서 고아로 종료될 수 있다. 창이 몇 초라 받아들인다. 발생하면 원장에 `orphan`으로 남으니 측정창에서 센다.
## 측정 지표와 측정창
머지 후 파드 실행 10회 또는 7일 중 먼저 오는 쪽. 근거는 cloud.yml 로그와 `ops:budget/ledger.jsonl`뿐이다.
- 동시에 돈 파드 수의 최대치(원장 start/end 시각).
- 원장 무결성: 모든 start에 대응하는 end가 있다. 두 run이 겹친 구간에서 줄이 빠지지 않는다(run 로그의 "result saved"·"pod … completed"와 대조).
- `over_cap`·`orphan` 발생 건수와 그 비용.
## 성공 기준 (수치)
- 동시 파드 ≥ 2를 1회 이상 관측한다.
- 원장 줄 누락 0건.
- 월 합계 ≤ 상한(`month_total`).
- 경합 때문에 생긴 `orphan` 0건.
## 롤백 방법
이 PR을 revert하면 단일 그룹 직렬로 돌아간다. union 속성은 러너 로컬 설정이라 남지 않는다.
## 결과
(측정창 종료 후 auditor가 기록)
