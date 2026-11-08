# 034: Bash guard 훅을 절대 경로(`$CLAUDE_PROJECT_DIR`)로 — cwd가 web/로 바뀌어도 Bash가 막히지 않게
- 상태: 진행 중
- 제안: auditor, 2026-11-08 / 이슈 #659 / PR (이 PR)
## 문제 (관측 근거: ops journal 11-01~11-07, ops:reports/2026-W45.md, STATE 경보 11-04 13:15Z·11-06 12:45Z·11-07 13:05Z·15:30Z)
`.claude/settings.json`의 PreToolUse 훅 명령이 `python harness/hooks/guard_bash.py`(상대 경로)였다. 셸 cwd가 `web/e2e`·`web/app`로
바뀌면 훅 스크립트를 찾지 못해 그 뒤 모든 Bash 호출이 훅 실패로 거부됐다.
- journal friction 중 "guard 훅 상대 경로로 Bash 전체 차단" 22건(7일). builder 11-05·11-06(2회)·11-07(3회), builder-b 11-01·11-07.
- 매번 `web/*/harness/hooks/` 임시 shim 파일을 만들어 탈출했다(shim이 커밋될 위험).
- PR #552: builder-b가 수정 푸시에 3번 실패해 11-03 15:16Z~11-04 12:20Z 정체, 그 사이 reviewer-b no_work 스윕 7회.
- planner 경보에서 "harness-change 최우선 후보"로 반복 지목.
## 가설
훅 명령을 `python "$CLAUDE_PROJECT_DIR/harness/hooks/guard_bash.py"`로 바꾸면 cwd 이동이 Bash 전체 차단으로 번지지 않는다.
## 변경
- `.claude/settings.json` 훅 명령 한 줄.
- `tests/test_harness.py`: 모든 훅 `command`가 `"$CLAUDE_PROJECT_DIR/harness/..."`를 쓰고 상대 `harness/`를 쓰지 않는지,
  훅을 하위 디렉터리(`<tmp>/web/e2e`)에서 `CLAUDE_PROJECT_DIR=<루트>`로 실행해 `ls` exit 0·force push exit 2인지 확인(변경 전 설정에서 실패).
## 측정 지표와 측정창 (머지 후 7일)
1. journal friction 중 guard 훅 경로·cwd 때문에 Bash가 막혔다는 보고 수
2. 임시 shim을 썼다는 보고 수
3. 같은 원인으로 수정 푸시에 실패한 PR 수
## 성공 기준 (수치)
(1) 0~1건(기준선: 7일 22건, builder 계열 실사건 12건), (2) 0건, (3) 0건.
guard 차단 기능 회귀 없음(force push·main push 차단 테스트 유지).
## 롤백 방법
이 PR revert.
## 결과 (측정창 종료 후 기록)
