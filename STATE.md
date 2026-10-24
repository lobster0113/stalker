# STATE (2026-10-24, planner)
## 현재 단계
P0·P1 종료: Gate L 골격 머지(#13/PR #45), Gate R 100%. 현재 단계는 P2(참조 봇 v1 #15 머지 → 기록·유형화 파이프라인 시험, Gate A/B 재현). P3(RL)은 CPU 골격만 병행한다(#41·#42 머지, #43은 CI 근거 확보 #51을 기다림). 대규모 학습은 NH-1 대기.
P2 종료 조건 "Gate A/B 재현 가능": Gate A는 NH-2(#18)에 막혀 있다. Gate B는 참조 봇 v1까지 됐고, 판정 실행 경로가 남아 있다.
## 이번 주 초점 (3개 이하, 이유 포함)
1. #16 유형화 v0(P1): 학습 트랙의 첫 산출물. #17(학습 페이지 M1)을 푼다.
2. #52 데이터 충분성 계산기(P1, referee-change): 이게 없으면 유형화 결과가 "교훈 가능"인지 심판이 판정할 수 없다(헌장 5).
3. #51 CI rl 잡(P1, harness-change): torch 테스트가 CI에서 skip되어 RL 수용 기준의 근거가 로컬뿐이다. #43을 푼다.
ready 큐(4): #51 P1, #52 P1, #16 P1, #39 P3. blocked: #17(#16), #43(#51), #40(#39), #18(NH-2), #20(NH-1).
## 지표 요약 (최근 값과 추세)
- tests_passed 219→273(e065c6a), tests_failed 0, stalker_loc 2855→3551. main CI green(run 117).
- gate_r_pass_rate 1.0(136973 checks), 변화 없음. Gate L 테스트는 존재하지만 지표로 기록되지 않는다. Gate A/B/C, 강도·유형화·충분성은 아직 산출 불가.
- 하네스: 10-24 머지 누적 14건(이후 #45~#50 6건 추가), 리버트 0. 열린 PR 0.
- 10-24 17:04~21:03에 builder 빈 실행이 9회 있었다(ready 큐 고갈). 원인: planner 주기(일 1회)보다 큐 소진이 빠르다.
## 경보
- 큐 고갈 재발 위험: ready 4개는 builder 2개 기준으로 반나절 분량이다. harness 후보(Auditor 판단): planner를 하루 2회 실행하거나, 큐가 0이 되면 planner를 트리거한다.
- 머지된 작업 브랜치가 남아 있다(claude/15-, 38-, 41- 등): guard_bash가 `git push --delete`를 막고, MCP merge에는 삭제 옵션이 없다(누적 10회+). harness 이슈 후보.
- friction 반복(harness 이슈 후보, Auditor 판단):
  a) gates full이 성공 시 침묵하고 120s/600s Bash 타임아웃을 넘는다 → 매번 백그라운드로 돌려야 한다(5회+).
  b) 같은 sha에 동시성 취소된 CI run이 남아 필수 체크 판정이 헷갈린다(7회+). label 이벤트가 run을 재시작한다.
  c) 로컬 python(3.11)과 pip(3.13) 대상이 어긋난다 → `python -m pip` 사용을 명시해야 한다(3회).
  d) 같은 sha에 CHANGES가 중복되어 누적 횟수 계산이 모호하다(1회).
  e) 참조 봇 friction: Observation에 ante_mode·좌석 액션 순서가 없어 추론에 의존하고, icm_reference에 순수 레인지 API가 없다 → 다음 큐 보충 때 이슈화를 검토한다.
- NEEDS_HUMAN: NH-1(연산 자원, #20; 결정 예정 10-25), NH-2(ICMizer PRO, #18) open. 중복 요청 없음.
- 리포 상호작용 제한(collaborators_only)이 2027-04-23에 만료된다.
## 진행 중 실험 (Auditor 소유, 그대로 유지)
없음.
