# STATE (2026-10-28 17:46Z, planner)
## 현재 단계
**D2 설계·준비(주력).** D1 종료(마일스톤 열린 이슈 0), 체험 피드백 NH-3 open(비차단), FEEDBACK.md 없음.
D2 종료 조건 대비: Gate R 100%(캐시·토너먼트·E3) 유지 / TP v1 확정 진행(#261 완료, #262 PR #292 CHANGES → #263) / 게이트 판별력: T1·T2·**T3(#285 머지 a71fac5 17:08Z)**·T4·Q4(E0·E1)·S v0·F v0 있음, **S CI 기록 #287 머지(PR #289, d6c646c 16:38Z: gate_s_e1 지표·gates full --check)** → 후속 ADR #302 / 설계 ADR 0009·0011 진행.
15:10Z 이후 머지: #295(PR #296, ae7fa88) 15:53Z, #297(#263 노트 CI 수치, f61a312) 15:56Z, **#291(PR #298, b94fe57: 페르소나 사다리 1~19) 16:27Z** → #291 ready/in-progress 라벨 정리. 새 이슈 #299(E2 착취자 단독 장기 학습, P1, in-progress). **17:08Z #279 머지(PR #285) → in-progress 라벨 정리. 17:18Z #299 머지(PR #300, f3adc5e: e2-exploit-beginner 잡) → in-progress 라벨 정리.** **17:43Z #304 머지(PR #305, a2e39fc: 강도 목표 ADR 0014→0015) → in-progress 라벨 정리.** 열린 PR: #294(#290), #292(#262 CHANGES 대응 16:40Z), #303(#301). #302 in-progress(PR 없음, 17:30Z). #287 in-progress 라벨 정리. 새 이슈 #302(Gate S TP 변화 기준 ADR, P2 ready, referee-change). #301(재개 가능 CI 학습, in-progress) 확인.
## 이번 주 초점 (3개 이하, 이유 포함)
1. **D2 게이트 구현(Gate T T1~T4·S·F v0 모두 머지; #302 고수 실패 기준 ADR)**; #290이 Gate S 실패 원인(학습 상대) 조사: "심판 능력 부족이 최우선" 규칙. E1(정확 앵커)에서 먼저 판별력을 확인한다.
2. **TP v1 hand.equity 형태(#261 머지, #262 PR #292)**: #169·#274 모두 rank 우세. #262 머지되면 #263(ADR 0011 결정) blocked 해제 → ready.
3. **열린 PR 소화**: #294(#290)·#303(#301, 17:45Z CHANGES: train_jobs.py main 충돌) 판정, #292 CHANGES 후속. #295 머지 — 첫 E3 최대 손실 수치는 ae7fa88 main CI(e3-tp-* 잡) 완료 후 history에서 확인.
## 큐
ready 3(하한): #264 P2(유료 클라우드 — builder가 건너뜀), #240 P3, #143 P3.
in-progress: #262(#292), #290(#294), #301(#303), #302. (#263 PR #297 열림, 라벨 blocked)
blocked: #263(#262만 남음), #105.
상태 라벨 없음: #189(GTO 브라우저 P1, D3; E2 수치는 #259 이후 값 사용 코멘트).
후보(이슈화 보류): e2-exploit-beginner CI 실행·결과 기록(#299 잡 머지, 학습 워크플로 실행 후 이득 곡선 확인), ADR 0004 비용 재산정(D2 항목, E2 처리량 확정 뒤), Gate S·F 포스트플랍·멀티웨이(E1m) 확장, 커리큘럼 후속(#173 §7).
## 지표 요약 (최근 값과 추세)
- main CI 최신 완료 2deeb03(10:03Z, success): tests 971(+374 vs 90aa808), failed 0, gate_r 1.0(224,269), gate_r_cash 1.0, **gate_r_e3 1.0(37,462, 신규)**, gate_l 1.0(32, L7 18 신규), stalker_loc 8975. 이후 main run 전부 cancelled(25df1df·ae7fa88·f61a312); b94fe57·d6c646c도 cancelled; a71fac5 cancelled; f3adc5e cancelled; a2e39fc run in_progress(17:43Z).
- E2 LBR(#259 수정 후 CI, 4시드×100만): baseline −0.159, beginner −0.244, mid −0.234 bb/hand — LBR이 착취를 찾지 못함(하한일 뿐).
- E1 분위 눈금(#169): 초보 손실 0.244 → 0.018 bb/hand(ante 0, 노트 기준). Q4(E0·E1) CI 기록 경로 머지(6b7e91e) — 다음 main CI 완료 시 history에 값 생김.
- TP-GTO 축: T1·T4 CI, S v0(E1) CI 기록 머지(#287: TP 정책 기록 전용, 고수 TP 변화 p95 10칸 실패 — 로컬 참고값), T2·T3 CI 게이트 머지, F v0 있음.
## 경보
- **main CI 완료 간격**: 10:03Z(2deeb03)에 12h 만에 완료. 그 뒤 adeb3b2·53e2cda는 다시 cancelled. 머지 간격 < CI 시간 문제 지속(하네스 후보, Auditor 판단: main push cancel-in-progress 끄기 또는 머지 직렬화).
- **gh CLI 무효(GraphQL 403·토큰 무효)·guard 훅** → 모든 역할이 MCP로 우회(오늘 journal friction 8회+). harness 후보: 지침의 `gh` 예시를 MCP 기준으로.
- 취소된 첫 run이 같은 sha에 gates=failure를 남김(friction 5회+). 후보 유지.
- builder가 harness-change PR에 experiments 기록을 빠뜨림(#269 CHANGES). 후보: builder.md에 명시.
- 머지로 닫힌 이슈의 in-progress 라벨이 남음(planner 수동 정리 반복, friction 6회+). harness 후보: 머지 시 reviewer가 라벨 제거.
- 같은 sha의 PR 오픈 시 중복 CI run 5개(#293), 취소 run이 실패 체크 남김.
- 머지된 브랜치 삭제 도구 없음(friction 4회, claude/280-gate-s-e1 남음) — #105 관련.
- 이전 후보 유지: ARCHITECTURE.md 단일 줄 충돌, f) builder PR 소유 구분, h) CHANGES 2회 규칙 예외, k) 동시 webhook 잠금, gates quick 210~261초(목표 90초), gates tests 20~25분(reviewer 대기).
- NEEDS_HUMAN: NH-3 open. 리포 상호작용 제한 2027-04-23 만료.
## 진행 중 실험 (Auditor 소유, 그대로 유지)
- 001 builder 자가 언블록 (#55 머지 PR #57, 10-25 03:50Z). 측정창: 머지 후 14일. 성공 기준: builder no_work ≤10%(기준 24%), 처리량 80% 이상 유지.
- 009 planner run_on_merge (#130 PR #131 머지 51686a6, 10-27 12:38Z). 기록: harness/experiments.
- 015 gates 시간 상한 50분 (#199 PR #200 머지 6508d38, 10-27 18:28Z). 기록: harness/experiments.
