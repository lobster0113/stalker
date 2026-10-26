# 루틴 구성

클라우드 루틴(Claude Code routines)의 **실제 트리거**는 고정이고 자주 깨어난다. 각 실행은 시작하자마자
`python harness/should_run.py <role>`로 `harness/schedule.json`을 확인해서 실제로 일할지 결정한다.
RUN이면 같은 role 잠금(`ops:locks/<role>.json`)도 함께 잡는다. 실행은 journal 기록 직후 `--release`로 푼다(`PROTOCOL.md` §6).
→ 실제 운영 주기는 리포 안의 `schedule.json`으로 통제되며, Auditor가 `harness-change` 실험 PR로 조정할 수 있다
(루틴 설정 자체를 바꾸지 않고도 L2가 주기를 진화시킬 수 있게 하기 위함).

| 루틴 | 고정 트리거 (UTC) | 기본 실효 주기(`schedule.json`) | 모델 | 지침 |
|---|---|---|---|---|
| builder | 매시 :00 | 1시간 | opus-5.5 | `routines/builder.md` |
| builder-b | 매시 :20 | 1시간 | sonnet-5.5 | `routines/builder.md` (병렬 2번째 빌더) |
| reviewer | PR opened/synchronize/reopened + 매시 :40 스윕 | 이벤트 즉시, 스윕 1시간 | opus-5.5 | `routines/reviewer.md` |
| planner | 15분마다 (`*/15 * * * *`, 사용자 요청 2026-10-27) | 10시간. 단 main에 마지막 실행보다 새 커밋(머지)이 있으면 즉시 실행(`run_on_merge`), ready ≤ `ready_floor`(1)이면 마지막 실행 2시간(`queue_low_min_hours`) 뒤부터 조기 실행(실험 008). 잠금으로 동시 실행 방지 | opus-5.5 | `routines/planner.md` |
| researcher | 화·금 00:00 (09:00 KST) | 68시간 | sonnet-5.5 | `routines/researcher.md` |
| gardener | 목 00:00 | 7일 | sonnet-5.5 | `routines/gardener.md` |
| auditor | 일 00:00 | 7일 | opus-5.5 | `routines/auditor.md` |

변경 이력: 2026-10-24 사용자 요청("주기가 너무 느슨, 1주 내 첫 결과물")으로 빌더 2개·1시간 주기로 상향.
사용량 한도(Max 5x)에 걸리면 Auditor가 journal의 실패/지연을 근거로 `schedule.json`을 조정한다.

## 루틴 공통 프롬프트 (루틴에 등록된 고정 문구)
```
You are the STALKER <role> routine running autonomously; no human will answer questions.
1. Run: python harness/should_run.py <role>   (reviewer: add --sweep unless this run was fired by a pull_request event)
   If it prints SKIP, stop immediately without doing anything else.
2. Read CLAUDE.md.
3. Follow harness/routines/<role>.md exactly. Communicate only through GitHub and the ops branch as described in harness/PROTOCOL.md.
```
등록 상태(트리거 ID 등)는 `ops:ROUTINES_REGISTRY.md`에 기록한다.
