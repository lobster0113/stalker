# 011: UI 스크린샷 리뷰 경로와 사용자 체험 피드백 흐름
- 상태: 진행 중
- 제안: planner, 2026-10-26 / 이슈 #106 / PR (이 PR)
## 문제
방향 전환(ADR 0008, 실험 004) 뒤 UI 품질이 헌장 요구(7)가 됐지만, 하네스가 그것을 판단할 경로가 비어 있다.
- reviewer.md 9항은 "스크린샷 아티팩트를 받아 직접 본다"고만 하고 받는 방법이 없다. CI 아티팩트 압축은 `*.blob.core.windows.net`에서 내려오는데 클라우드 루틴 프록시가 막는다(reviewer journal 2026-10-27T03:05Z 6건 friction "CI artifact blob download blocked by proxy", STATE 경보 e). 2026-10-27 04:10Z 재확인: run 40440179339 아티팩트 12705983768 → REST 302 → blob `CONNECT tunnel failed, response 403`.
- 사용자 체험 피드백은 NH-3에 한 줄("나중에 수정 요청 예정")로만 남고, 받은 피드백을 어디에 적고 누가 이슈로 바꾸는지 정해져 있지 않다.
## 가설
(1) Reviewer에게 받는 명령과 막혔을 때의 대체 절차(로컬 Playwright로 같은 15장 생성)를 주면 UI PR 판정마다 실제 화면을 본 기록이 남는다. (2) 피드백을 `ops:FEEDBACK.md`에 원문으로 남기고 Planner가 매 실행 open 항목을 이슈로 바꾸게 하면 피드백이 사라지지 않고 빨리 이슈가 된다.
## 변경
- `harness/routines/reviewer.md` 9항: REST `actions/runs?head_sha=` → `runs/{id}/artifacts` → `artifacts/{id}/zip` 명령, 403이면 `web/e2e` 로컬 실행(서브셸 cd, `CHROMIUM_PATH=/opt/pw-browsers/chromium`), 판정 코멘트에 확인 경로·장수·관찰 기록. CI `web` 잡 실패도 `CHANGES`로 명시.
- `harness/PROTOCOL.md` §1 표에 `ops:FEEDBACK.md`, §9에 체험 피드백 흐름(게시 → NEEDS_HUMAN 요청 → 대화 세션이 원문 기록 → Planner 이슈화)과 FB 항목 형식.
- `harness/routines/planner.md`: 0단계 읽기에 `ops:FEEDBACK.md`, 2단계에 open 피드백 처리.
## 시연 (2026-10-27, builder, #99 결과물 = main 311b056)
- 받기: run 40440179339(ci, push, success)의 `web-screenshots`(3.3MB) — 목록 조회 성공, blob 다운로드 403. 대체 절차로 진행.
- 대체: `web/e2e`에서 `npm ci` + `npm test` → `Gate U ok`, 15장 생성. 읽은 화면: `train-input-phone`(TP 패널이 바텀 시트, 제출 버튼 고정, 가로 넘침 없음), `train-result-laptop`(테이블 중앙·채점 패널 오른쪽, 폴드한 Maya의 카드 뒷면이 이름판 위에 겹쳐 남음 — 사소한 관찰).
## 측정 지표와 측정창
머지 후 14일. (1) `area:service` PR의 판정 코멘트 중 스크린샷 확인 기록(경로·장수)이 있는 비율, (2) `ops:FEEDBACK.md` 항목 기록 → `issued`/`declined`까지의 리드타임, (3) 그 기간 `open`으로 48시간 넘게 남은 피드백 수.
## 성공 기준
(1) ≥ 90%, (2) 중앙값 ≤ 24시간, (3) 0. 측정창 안에 `area:service` PR 판정이 3건 미만이거나 피드백 항목이 없으면 "판단 불가"로 기록하고 측정창을 14일 연장한다.
## 롤백 방법
이 PR을 revert(문서만 바뀐다. `ops:FEEDBACK.md`는 남겨도 해가 없다).
## 결과
(측정창 종료 후 auditor가 기록)
