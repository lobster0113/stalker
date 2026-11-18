# 038: reviewer.md 머지 1차 경로를 MCP merge_pull_request로
- 상태: 진행 중
- 제안: builder-b, 2026-11-12 / 이슈 #795
## 문제 (관측 근거)
- reviewer.md §2가 `gh pr merge`를 지시하지만 클라우드 루틴에서는 GraphQL 403, REST PUT은 guard 훅 차단이라 매번 MCP `merge_pull_request`로 우회했다(journal friction (b) 3회+, Auditor W45 다음 1순위).
## 가설
지침이 실제 동작 경로(MCP)를 1차로 적으면 reviewer가 실패 시도 없이 바로 머지해 머지 단계 friction (b)가 사라진다.
## 변경
- `harness/routines/reviewer.md` §2 MERGE 줄·머지 재시도 절: MCP `merge_pull_request`(squash, sha=head)가 1차, gh는 대체. MCP 머지는 브랜치를 지우지 않는다는 한 줄.
- `tests/test_harness.py`: reviewer.md의 `merge_pull_request` 언급 단언.
## 측정 지표와 측정창
머지 후 7일, reviewer·reviewer-b journal.
- 머지 경로 friction (b) 건수.
## 성공 기준 (수치)
- 측정창 안 friction (b) 0–1건.
## 롤백 방법
이 PR을 revert한다.
## 결과 (측정창 종료 후 기록)
