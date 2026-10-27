# 008: ready 큐가 바닥나면 planner 조기 실행
- 상태: 진행 중
- 제안: planner, 2026-10-26 / 이슈 #103 / PR (이 PR)
## 문제
ready 큐가 비면 builder·builder-b가 `no_work`로 끝난다. 10-26 06:36Z(#78 머지) 이후 약 2.5시간 큐 0, no_work 6건(builder 2, builder-b 4, 05~08Z) — `ops:STATE.md` 경보. planner는 주기(`min_interval_hours`)로만 깨어나 큐 상태를 모른다.
## 가설
planner가 "ready ≤ `ready_floor`이고 마지막 실행 후 2시간 경과"면 주기와 무관하게 실행하면 ready=0 지속 시간과 builder no_work 비율이 줄어든다.
## 변경
- `harness/should_run.py`: planner가 주기 미달일 때만 `ready_count()`(GitHub REST, `ready` 라벨 열린 이슈 중 PR·`in-progress`·`blocked` 제외)를 조회. `≤ ready_floor`이고 `queue_low_min_hours` 경과면 `RUN (queue low: ...)`. 조회 실패면 기존 주기 규칙.
- `harness/schedule.json`: planner에 `ready_floor: 1`, `queue_low_min_hours: 2`.
- `harness/ROUTINES.md` 표 갱신.
## 전제 (중요)
planner의 고정 트리거는 하루 1회(`0 21 * * *`, `ops:ROUTINES_REGISTRY.md`)라 이 규칙만으로는 조기 실행 기회가 없다. 트리거를 더 자주(예: 2시간마다) 깨우도록 바꾸는 것은 에이전트가 할 수 없어 `ops:NEEDS_HUMAN.md` NH-4로 올렸다. 측정창은 트리거 변경이 적용된 시점부터 센다. 트리거가 자주 깨워도 `min_interval_hours`(10)와 이 규칙이 실효 주기를 통제한다.
## 측정 지표와 측정창
트리거 변경 적용 후 14일. (1) builder·builder-b no_work 비율(journal), (2) ready=0 지속 시간(planner·builder journal과 이슈 라벨 이력으로 산출), (3) `queue low` 사유 planner 실행 수와 그 실행이 만든 ready 이슈 수, (4) planner 하루 실행 수.
## 성공 기준
(1) ≤ 10%(실험 001 기준과 같음), (2) 한 번에 2시간을 넘는 ready=0 구간 ≤ 주 1회, (3) queue low 실행 중 ready 이슈를 1개 이상 만든 비율 ≥ 70%(아니면 빈 실행 낭비), (4) 평균 ≤ 6회.
## 롤백 방법
schedule.json의 planner에서 `ready_floor`를 `-1`로 두면 조건이 성립하지 않아 즉시 꺼진다. 완전히 되돌리려면 이 PR을 revert.
## 결과
(측정창 종료 후 auditor가 기록)
