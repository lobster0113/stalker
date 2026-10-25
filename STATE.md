# STATE (2026-10-25, planner)
## 현재 단계
P2. Gate B 판정 경로(#61)·유형화↔충분성(#62)·Gate L 지표(#63)·action_values(#64)·Observation 필드(#65)·Recurrent PPO(#43)가 머지됐다. 남은 P2 종료 조건은 "Gate A 재현 가능"이다. 실물 ICMizer는 NH-2(#18) 대기라 참조기 기준 Gate A(#72→#73)로 먼저 진행한다. Gate B는 실행 경로가 있으나 실제 후보(RL) 판정은 #76 이후, 전체 명세 실행은 NH-1 대기. 단계 전환은 없다.
## 이번 주 초점 (3개 이하, 이유 포함)
1. #72 → #73 Gate A 스팟 세트 v1과 판정 경로(P1, referee-change): P2의 마지막 종료 조건이다. 레벨 1 판정의 필수 축이다.
2. #74 S1 rule-of-three(P2, referee-change), #77 충분성 지표 CI 기록(P2, referee-change): 데이터 충분성 축이 아직 지표로 나오지 않는다. 결정론적 소표본 셀을 정밀하다고 판정하는 오류도 심판에서 바로잡는다.
3. #75 Gate L L2·L6 활성화(P2, referee-change), #76 RL Gate B 후보(P2): RL 트랙을 판정 경로에 연결한다.
ready 큐(7): #72 P1, #73 P1(선행 #72), #74 P2, #75 P2, #76 P2, #77 P2, #78 P3(실험). blocked: #18(NH-2), #20(NH-1).
## 지표 요약 (최근 값과 추세)
- tests_passed 329→350(b598ced), tests_failed 0, stalker_loc 4088→4439. main CI green(run 188, b598ced).
- gate_r_pass_rate 1.0(136973 checks), 변화 없음. gate_l_pass_rate 1.0(14 checks: L1 4/4, L3 3/3, L4 3/3, L5 4/4). L2·L6은 기록되지 않는다(#75).
- Gate A/B/C 결과, 강도·충분성 지표는 아직 산출하지 못한다(#73·#76·#77 이후). 로컬 참고값: sng6 30게임 853셀 중 lessonable 0(PR #68).
- 하네스: 10-25 09:09 이후 머지 6건(#66~#71), 리버트 0, CHANGES 2회(#66·#71, 각 1라운드). 열린 PR 0.
## 경보
- [planner 10-25 21Z] ready 큐가 16:08Z 머지 이후 약 5시간 0이었다. builder no_work 3건·builder-b no_work 3건이 이어졌다(실험 001 측정창 안). 신규 7건으로 보충했다. planner 일 1회 주기로는 하루 처리량(6~7건)을 따라가지 못한다. 하네스 후보(Auditor 판단): ready ≤1이면 planner 트리거, 또는 일 2회.
- [auditor 10-25] 무결성 감사 위반 0(머지 21건). 리포트 `reports/2026-W43.md`.
- [auditor 10-25] reviewer 동시 실행으로 같은 PR에 판정이 중복된다(#50·#53·#57·#59). should_run에 PR별 잠금이 없다. 실험 후보.
- 머지된 작업 브랜치가 남아 있다(claude/16-, 17-, 40-, 43-, 55-, 61-~65- 등). guard_bash가 `git push --delete`를 강제 푸시로 막고 MCP merge에는 삭제 옵션이 없다(누적 20회+). 하네스 이슈 후보.
- friction 반복(하네스 이슈 후보, Auditor 판단):
  a) gates quick/full이 성공 시 침묵하고 120s 포그라운드 타임아웃을 넘는다(10-25 오후에만 6회+, quick 포함).
  b) label 이벤트가 CI를 재시작해 같은 sha에 동시성 취소 run이 남는다(10회+).
  c) guard가 이벤트 base.sha와 diff해서 base가 움직이면 보호 경로를 오탐한다(#54). merge-base 사용 후보(referee-change).
  d) harness-change 작업의 실험 기록 요구가 reviewer.md에만 있다(#54·#58).
  e) PR 본문만 고친 지적은 새 커밋이 없어 sweep이 재판정하지 않는다(#54).
  f) gh CLI 미인증(GraphQL 403). REST/MCP로 우회한다(매 reviewer 실행).
  g) 이슈 수용 기준에 main push 후에만 측정 가능한 항목이 있었다(#63). planner는 이런 항목을 "머지 후 확인"으로 분리한다(#77에 적용).
- NEEDS_HUMAN: NH-1(연산 자원, #20; 결정 예정 10-25, 아직 open), NH-2(ICMizer PRO, #18) open. 중복 요청 없음.
- 리포 상호작용 제한(collaborators_only)이 2027-04-23에 만료된다.
## 진행 중 실험 (Auditor 소유, 그대로 유지)
- 001 builder 자가 언블록 (#55 머지 PR #57, 10-25 03:50Z). 측정창: 머지 후 14일. 성공 기준: builder no_work ≤10%(기준 24%), 처리량 80% 이상 유지.
