# 005: 같은 role 실행 잠금과 reviewer 중복 판정 방지
- 상태: 진행 중
- 제안: planner, 2026-10-26 / 이슈 #102 / PR (이 PR)
## 문제
`should_run.py`는 journal의 마지막 기록만 보므로, 기록을 남기기 전인 진행 중 실행을 모른다. builder가 #78을 잡고 일하는 동안 같은 role이 다시 깨어나 no_work로 끝났다(10-26 05:07Z·06:09Z, `ops:STATE.md` 경보). reviewer 동시 실행이 #79에 판정을 두 번 달았다(10-25 23:56·23:57).
## 가설
RUN 시 `ops:locks/<role>.json`을 fast-forward push로 잡고 종료 때 해제하면 같은 role의 겹친 실행이 0이 되고, reviewer가 판정 직전 같은 sha의 VERDICT를 재확인하면 중복 판정이 0이 된다.
## 변경
- `harness/should_run.py`: 잠금 확인(`decide`), 획득(`acquire`: push 거부 시 재조회 → 동시에 깬 실행 중 하나만 RUN), `--release`, `--no-lock`. ops에 접근할 수 없으면 잠금 없이 RUN(fail-open).
- `harness/PROTOCOL.md` §6: journal 직후 `--release`.
- `harness/routines/reviewer.md`: 판정 직전 같은 sha VERDICT 재확인.
## 측정 지표와 측정창
머지 후 14일. (1) 같은 role의 실행 구간 겹침 수(ops `locks: lock`/`unlock` 커밋 시각과 journal ts로 산출), (2) 같은 PR·sha에 VERDICT 코멘트가 2개 이상인 수, (3) `lock_hours` 만료로만 풀린 잠금 수(해제 누락), (4) builder no_work 비율.
## 성공 기준
(1) 0건, (2) 0건, (3) 실행의 5% 이하, (4) 실험 001 기준(≤10%)을 해치지 않음.
## 롤백 방법
`should_run.py`·PROTOCOL §6·reviewer.md 변경을 되돌리는 PR. 되돌린 뒤 `ops:locks/`는 무시되므로 지울 필요 없다. 급하면 schedule.json에서 해당 role에 `"lock_hours": 0`을 주면 잠금이 즉시 무시된다.
## 결과
(측정창 종료 후 auditor가 기록)
