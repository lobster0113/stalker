# 하네스 프로토콜 (모든 역할 공통)

## 1. 저장소 구조
| 위치 | 용도 | 누가 쓰나 |
|---|---|---|
| `main` | 제품·심판·하네스 코드. PR로만 변경 | Builder(PR), Reviewer(머지) |
| `ops` 브랜치 | 운영 데이터. 리뷰 없이 직접 커밋(append 위주) | 아래 표 |
| `ops:STATE.md` | 현재 초점, 진행 중 실험, 최근 경보 | Planner, Auditor |
| `ops:journal/YYYY-MM.jsonl` | 루틴 실행 기록 (§6) | 모든 루틴 |
| `ops:metrics/history.jsonl` | 지표 시계열 | **CI 전용** (에이전트 수정 금지) |
| `ops:reports/` | 하네스 건강 리포트 | Auditor |

`ops`에 쓰는 법:
```bash
git fetch origin ops && git worktree add ../ops origin/ops -B ops   # 또는 기존 worktree 갱신
# 파일 수정 후
git -C ../ops add -A && git -C ../ops commit -m "<role>: <요약>" && git -C ../ops push origin ops
# push 거부 시: git -C ../ops pull --rebase origin ops 후 재시도 (최대 3회)
```

## 2. 라벨
- 상태: `ready`(착수 가능) · `in-progress`(누가 잡음) · `blocked`(선행 작업/정보 필요, 이유를 코멘트) · `needs-split`
- 우선순위: `P0`(main 고장·데이터 오염) · `P1` · `P2` · `P3`
- 영역: `area:engine` `area:ai` `area:records` `area:typing` `area:service` `area:referee` `area:harness` `area:docs`
- 종류: `kind:feature` `kind:bug` `kind:refactor` `kind:research` `kind:experiment` `kind:chore`
- 권한: `referee-change`(보호 경로 수정 허용) · `harness-change`(하네스 경로 수정 허용). **Planner·Auditor만 부여.**

## 3. 이슈 = 계약
모든 `ready` 이슈 본문은 이 형식을 따른다 (Planner 책임):
```
## 목표
한두 문장.
## 수용 기준 (모두 검증 가능해야 함)
- [ ] ...테스트/CI 체크/측정으로 확인 가능한 기준
## 범위 밖
- ...
## 선행
- #N (없으면 "없음")
## 참고
- 관련 문서/코드 경로
```
크기: Builder 한 번 실행(약 1~2시간)에 끝낼 수 있어야 한다. 아니면 `needs-split`.

## 4. 브랜치·커밋·PR
- 브랜치: `claude/<이슈번호>-<짧은-슬러그>`
- 커밋 메시지: `<area>: <무엇을> (#이슈)` — 영어 또는 한국어.
- PR 제목: `[#이슈] 요약`. 본문은 `.github/pull_request_template.md` 형식. `Closes #N` 필수.
- PR당 하나의 이슈. 범위 밖 변경 금지(발견한 문제는 새 이슈 제안을 PR 본문 "후속" 항목에).

## 5. 리뷰 판정 (Reviewer)
PR 코멘트 첫 줄이 정확히 다음 중 하나:
```
VERDICT: MERGE sha=<head 커밋 40자>
VERDICT: CHANGES sha=<head 커밋 40자>
VERDICT: CLOSE sha=<head 커밋 40자>
```
이어서 근거(수용 기준별 확인 결과, CI 수치, 지적 사항 목록). MERGE는 해당 sha의 모든 필수 체크가 success일 때만.
CHANGES가 2회 누적된 PR이 또 미달이면 CLOSE하고, 이슈에 `needs-split` + 실패 원인 코멘트.

## 6. Run journal
모든 루틴은 종료 직전 `ops:journal/YYYY-MM.jsonl`에 한 줄(JSON) append:
```json
{"ts":"2026-10-24T12:00:00Z","role":"builder","outcome":"pr_opened|merged|changes|closed|no_work|blocked|failed|paused","issue":12,"pr":34,"notes":"한 줄 요약","friction":"하네스 때문에 막히거나 헷갈린 점(없으면 빈 문자열)"}
```
`friction`은 L2(Auditor)가 하네스를 개선하는 핵심 입력이다. 솔직하게 쓴다.

## 7. 잡기(claim)와 동시성
- 이슈를 잡을 때 `in-progress` 라벨 + 코멘트 `CLAIM <role> <UTC시각>`.
- 6시간 넘게 PR 없이 `in-progress`인 이슈는 다른 실행이 회수 가능(코멘트 `RECLAIM`).
- 열린 Builder PR이 2개 이상이면 Builder는 새 이슈를 잡지 않고 기존 PR 후속만 한다.

## 8. 에스컬레이션
사람에게 묻지 않는다. 결정이 필요하면: 선택지·근거·추천을 담은 ADR(`docs/decisions/NNNN-*.md`)을 작성해 PR로 올리고, 추천안으로 진행한다. Reviewer가 판정한다.
