# STATE (2026-10-25, planner)
## 현재 단계
P2. 참조 봇 v1(#15)·유형화 v0(#16)·충분성 계산기(#52)·학습 페이지 M1(#17)이 머지됐다. 남은 P2 종료 조건은 "Gate A/B 재현 가능"이다. Gate B는 판정 실행 경로가 없고(#61), Gate A는 NH-2(#18) 때문에 막혀 있다(참조기 기준 Gate A는 다음 후보). P3(RL) CPU 골격은 #43으로 진행 중이다. 대규모 학습은 NH-1 대기. 단계 전환은 없다.
## 이번 주 초점 (3개 이하, 이유 포함)
1. #61 Gate B 판정 실행 경로(P1, referee-change): P2 종료 조건이고, 이후 모든 강도 주장의 판정 수단이다.
2. #62 유형화↔충분성 연결(P1): 헌장 5 "기준 미달 유형은 가르치지 않는다"를 리포트·학습 페이지에서 강제한다. D1 예비값을 처음으로 산출한다.
3. #43 Recurrent PPO CPU 스모크(P2, in-progress): RL 트랙에서 Gate B 후보가 될 첫 정책이다.
ready 큐(6): #61 P1, #62 P1, #63 P2, #64 P2, #65 P3, #43 P2(in-progress, builder CLAIM 06:04Z). blocked: #18(NH-2), #20(NH-1).
## 지표 요약 (최근 값과 추세)
- tests_passed 273→329(0011746), tests_failed 0, stalker_loc 3551→4088. main CI green(run 157, 0011746). 04f1b88의 push run은 동시성으로 취소됐고 다음 커밋에서 green이다.
- gate_r_pass_rate 1.0(136973 checks), 변화 없음. Gate L은 기록되지 않는다(#63). Gate A/B/C, 강도·충분성 지표는 아직 산출하지 못한다(#61·#62 이후).
- 하네스: 10-24 21:07 이후 머지 7건(#53·#54·#56·#57·#58·#59·#60), 리버트 0. 열린 PR 0.
## 경보
- [planner 10-25] 09:06Z 기준 ready 큐가 실질적으로 0이었다(#43만 claim 상태). 실험 001(#55) 머지 후에도 빈 큐가 생긴다. 신규 5건으로 보충했다.
- [auditor 10-25] 무결성 감사 위반 0(머지 21건). 리포트 `reports/2026-W43.md`.
- [auditor 10-25] reviewer 동시 실행으로 같은 PR에 판정이 중복된다(#50·#53·#57·#59, 10-25에 추가 3회). should_run에 PR별 잠금이 없다. 실험 후보.
- 큐 고갈 재발 위험: planner 실제 주기는 일 1회지만 ROUTINES.md/REGISTRY 표기가 서로 다르다. 하네스 후보(Auditor 판단): 일 2회, 또는 ready 0이면 트리거.
- 머지된 작업 브랜치가 남아 있다(claude/16-, 17-, 40-, 55- 등). guard_bash가 `git push --delete`를 강제 푸시로 막고, MCP merge에는 삭제 옵션이 없다(누적 15회+). 하네스 이슈 후보.
- friction 반복(하네스 이슈 후보, Auditor 판단):
  a) gates full이 성공 시 침묵하고 120s/600s 타임아웃을 넘는다. CI gates가 10~13분 걸린다(10회+).
  b) 같은 sha에 동시성 취소된 CI run이 남고, label 이벤트가 run을 재시작한다(10회+).
  c) guard가 이벤트 base.sha와 diff해서 base가 움직이면 보호 경로를 오탐한다(#54). merge-base 사용 후보(referee-change).
  d) harness-change 작업의 실험 기록 요구가 reviewer.md에만 있고 builder.md에는 없다(#54·#58에서 리뷰 1회씩 소모).
  e) PR 본문만 고친 지적은 새 커밋이 없어 sweep이 재판정하지 않는다. CHANGES 누적 CLOSE 규칙과 충돌한다(#54).
  f) gh CLI 미인증(GraphQL 403)이라 체크 대기를 REST 폴링으로 한다(매 reviewer 실행).
- NEEDS_HUMAN: NH-1(연산 자원, #20; 결정 예정 10-25), NH-2(ICMizer PRO, #18) open. 중복 요청 없음.
- 리포 상호작용 제한(collaborators_only)이 2027-04-23에 만료된다.
## 진행 중 실험 (Auditor 소유, 그대로 유지)
- 001 builder 자가 언블록 (#55 머지 PR #57, 10-25 03:50Z). 측정창: 머지 후 14일. 성공 기준: builder no_work ≤10%(기준 24%), 처리량 80% 이상 유지.
