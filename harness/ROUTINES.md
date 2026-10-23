# 루틴 구성

클라우드 루틴(Claude Code routines)의 **실제 트리거**는 고정이고 자주 깨어난다. 각 실행은 시작하자마자
`python harness/should_run.py <role>`로 `harness/schedule.json`을 확인해서 실제로 일할지 결정한다.
→ 실제 운영 주기는 리포 안의 `schedule.json`으로 통제되며, Auditor가 `harness-change` 실험 PR로 조정할 수 있다
(루틴 설정 자체를 바꾸지 않고도 L2가 주기를 진화시킬 수 있게 하기 위함).

| 루틴 | 고정 트리거 | 기본 실효 주기(`schedule.json`) | 지침 |
|---|---|---|---|
| builder | 매시 정각 | 3시간 | `routines/builder.md` |
| reviewer | PR opened/synchronize/reopened + 매시 30분 스윕 | 이벤트 즉시, 스윕은 2시간 | `routines/reviewer.md` |
| planner | 매일 06:00 KST | 24시간 | `routines/planner.md` |
| researcher | 매주 화 09:00 KST | 7일 | `routines/researcher.md` |
| gardener | 매주 목 09:00 KST | 7일 | `routines/gardener.md` |
| auditor | 매주 일 09:00 KST | 7일 | `routines/auditor.md` |

## 루틴 공통 프롬프트 (루틴에 등록된 고정 문구)
```
You are the STALKER <role> routine running autonomously; no human will answer questions.
1. Run: python harness/should_run.py <role>   (reviewer: add --sweep unless this run was fired by a pull_request event)
   If it prints SKIP, stop immediately without doing anything else.
2. Read CLAUDE.md.
3. Follow harness/routines/<role>.md exactly. Communicate only through GitHub and the ops branch as described in harness/PROTOCOL.md.
```
등록 상태(트리거 ID 등)는 `ops:ROUTINES_REGISTRY.md`에 기록한다.
