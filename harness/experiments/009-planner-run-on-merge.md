# 009: 머지 직후 planner 실행 (run_on_merge)
- 상태: 진행 중
- 제안: 사용자 요청(대화 세션, 2026-10-27) / 이슈 #130 / PR #131
## 문제
planner가 10시간 주기와 큐 바닥 규칙(실험 008)으로만 깨어나서, 머지로 선행이 풀리거나 큐가 바뀌어도 다음 계획까지 몇 시간 걸린다. 사용자는 planner가 "PR이 되면 바로 다시 실행"되기를 요청했다.
## 가설
main에 마지막 planner 실행보다 새 커밋이 있으면 바로 실행하면, 머지 → 다음 이슈 준비(분할·언블록·ready 부여)까지의 지연이 줄고 builder no_work가 줄어든다. 새 머지가 없으면 깨어나도 SKIP이라 비용은 머지 수에 비례한다.
## 변경
- `harness/should_run.py`: `run_on_merge` 역할은 origin/main 최신 커밋 시각 > 마지막 실행이면 주기와 무관하게 RUN. 잠금이 우선.
- `harness/schedule.json`: planner `run_on_merge: true`.
- 트리거(대화 세션에서 적용, `ops:NEEDS_HUMAN.md` NH-4 resolved): PR 닫힘 webhook(`pull_request.closed`) + cron `5 * * * *`(API 최소 1시간).
## 측정 지표와 측정창
머지 후 7일. (1) 머지 시각 → 다음 planner 실행 시작까지 지연(중앙값), (2) planner 하루 실행 수, (3) `main updated` 사유 실행 중 이슈·라벨·STATE를 실제로 바꾼 비율, (4) builder·builder-b no_work 비율.
## 성공 기준
(1) 중앙값 ≤ 15분, (2) 평균 ≤ 12회/일, (3) ≥ 60%(아니면 빈 실행 낭비 → 조건을 "마일스톤·선행 관련 머지"로 좁힌다), (4) 실험 008 기준(≤ 10%) 유지.
## 롤백 방법
schedule.json의 planner에서 `run_on_merge`를 false로. 트리거 webhook은 대화 세션에서 제거.
## 결과
(측정창 종료 후 auditor가 기록)
