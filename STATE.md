# STATE (2026-10-24, planner)
## 현재 단계
P1 종료 기준 충족: Gate R 100%(CI e5d4ee7, gate_r_pass_rate=1.0, 136973 checks). P0 잔여는 Gate L 골격(#13)뿐 → #13 머지 시 P0 종료. 실질 작업 단계는 P2(참조 봇 v1·Gate A/B 재현)로 전환. P3(RL)은 CPU 골격만 병행(#41~#43), 대규모 학습은 NH-1 대기.
## 이번 주 초점 (3개 이하, 이유 포함)
1. #13 Gate L(P1) — P0 종료 조건. 기억 경계 심판 없이는 #43(RL)·Gate C를 판정할 수 없다.
2. #15 Gate B 참조 봇 v1(P1) — P2의 기준선. #16 유형화 → #17 학습 페이지(M1)를 푼다.
3. #41/#42 RL env·정책(P2) — P3 착수 준비. #43 PPO 스모크의 선행.
ready 큐(6): #13 P1, #15 P1, #41 P2, #42 P2, #38 P3, #44 P3.
## 지표 요약 (최근 값과 추세)
- tests_passed 119→219(10-24), tests_failed 0, stalker_loc 2020→2855. main CI green(e5d4ee7).
- gate_r_pass_rate 첫 산출 1.0(136973 checks). Gate L/A/B/C, 강도·유형화·충분성은 아직 산출 불가.
- 하네스: 10-24 머지 8건(#28,#29,#30,#31,#34,#35,#36,#37), CHANGES 3, CLOSE 1(#32 라벨 경합, 절차 문제), 리버트 0. 열린 PR 0.
## 경보
- 큐 정리(이번 실행): #13·#15 blocked→ready. #8 분해(#38 A / #39 B harness-change / #40 C) 후 닫음. #21 분해(#41/#42/#43) 후 닫음. #44 신규(ICM 참조기 후속). #16·#17은 #15 대기.
- NEEDS_HUMAN: NH-1(연산 자원, #20·대규모 학습; 결정 예정 10-25), NH-2(ICMizer PRO, #18) open.
- friction 반복(harness 이슈 후보, Auditor 판단):
  a) 머지된 작업 브랜치 삭제 불가 — guard_bash가 `git push --delete`를 강제 푸시로 오인하고, MCP merge에는 delete 옵션이 없다(누적 7회+).
  b) 보호 경로 PR 라벨 경합 — create_pull_request에 labels 인자가 없어 #32가 CLOSE됨(3회). 권고: builder.md에 draft→라벨→ready 순서를 명시하고, reviewer는 guard 재실행 후 판정.
  c) gates full이 성공 시 침묵해 slow 테스트 실행 여부를 확인할 수 없고, job log blob도 프록시에 막힘(3회). 권고: CI에 테스트별 요약 출력.
  d) 동시성 취소된 CI run이 체크 목록에 남음(5회). milestone 미조회(5회): builder는 P 라벨 우선.
  e) 심판이 차단 수준 엔진 버그를 찾았을 때의 규칙 부재(#27, 2회). 이번엔 P0 분리(#33)로 해결.
  f) 훅 상대경로(`python harness/hooks/guard_bash.py`) — cwd가 바뀌면 모든 Bash가 실패(1회, 영향 큼).
  g) 고정 시드 A/A 통계 테스트가 무관한 변경에도 ~5% 확률로 깨짐(2회).
- 로컬 Python 3.11 vs CI 3.12 차이(1회). PR CI가 낡은 base로 돎(1회).
- 리포 상호작용 제한(collaborators_only) 2027-04-23 만료.
## 진행 중 실험 (Auditor 소유, 그대로 유지)
없음.
