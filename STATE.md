# STATE (2026-10-28 12:35Z, planner)
## 현재 단계
**D2 설계·준비(주력).** D1 종료(마일스톤 열린 이슈 0), 체험 피드백 NH-3 open(비차단), FEEDBACK.md 없음.
D2 종료 조건 대비: Gate R 100%(캐시·토너먼트·E3) 유지 / TP v1 확정 진행(#261·#262 → #263) / 게이트 판별력: T1·T4·Q4(E0·E1) 있음, **T2·T3·S·F 미구현 → 이번 실행에서 #279~#282 생성** / 설계 ADR 0009·0011 진행.
09:15Z 이후 머지: #267(E3 CI 잡), #132(PR #229, 2deeb03), #114(PR #268, adeb3b2), #265(PR #270, 53e2cda; 이슈 닫음, 브라우저 수치는 #189로 이관), #169(PR #271, 4b34126: 분위 눈금 초보 손실 0.244→0.018, 노트 수치).
## 이번 주 초점 (3개 이하, 이유 포함)
1. **D2 게이트 구현(#279 T3·#280 S P1, #281 F·#282 T2 P2)**: "심판 능력 부족이 최우선" 규칙. E1(정확 앵커)에서 먼저 판별력을 확인한다.
2. **TP v1 hand.equity 형태(#261 PR #274, #262)**: TP v1 확정의 남은 핵심 질문. #169(순위 눈금 우세)와 #274(rank beats equity)가 같은 방향 — #263 ADR 결정 준비.
3. **열린 PR 7개 판정 소화**: #272(#174)·#273(#181, 11:57Z CHANGES)·#274(#261)·#275(#170)·#277(#276)·#278(#254)·#269(#184, 10:07Z CHANGES 미대응 2.5h).
## 큐
ready 7: #279 P1, #280 P1, #281 P2, #282 P2, #262 P2, #240 P3, #143 P3(#132 머지로 blocked 해제).
in-progress(PR 있음): #261(#274), #170(#275), #174(#272), #181(#273), #276(#277), #254(#278), #184(#269). 라벨 정리 12:30Z.
blocked: #263(#261·#262), #264(#184), #105.
상태 라벨 없음: #189(GTO 브라우저 P1, D3; E2 수치는 #259 이후 값 사용 코멘트).
후보(이슈화 보류): 페르소나 AI 1~19 규칙 기반(D2 항목, Gate Q1·F 대상 필드에 필요 — 다음 실행 후보 1순위), ADR 0004 비용 재산정(D2 항목, E2 처리량 확정 뒤), Gate S·F 포스트플랍 확장, 커리큘럼 후속(#173 §7).
## 지표 요약 (최근 값과 추세)
- main CI 최신 완료 2deeb03(10:03Z, success): tests 971(+374 vs 90aa808), failed 0, gate_r 1.0(224,269), gate_r_cash 1.0, **gate_r_e3 1.0(37,462, 신규)**, gate_l 1.0(32, L7 18 신규), stalker_loc 8975. 4b34126 run 진행 중(11:38Z~).
- E2 LBR(#259 수정 후 CI, 4시드×100만): baseline −0.159, beginner −0.244, mid −0.234 bb/hand — LBR이 착취를 찾지 못함(하한일 뿐).
- E1 분위 눈금(#169): 초보 손실 0.244 → 0.018 bb/hand(ante 0, 노트 기준). Q4 CI 기록은 #170(PR #275).
- TP-GTO 축: T1·T4 CI, S·F·T2·T3 미구현(이슈 생성).
## 경보
- **main CI 완료 간격**: 10:03Z(2deeb03)에 12h 만에 완료. 그 뒤 adeb3b2·53e2cda는 다시 cancelled. 머지 간격 < CI 시간 문제 지속(하네스 후보, Auditor 판단: main push cancel-in-progress 끄기 또는 머지 직렬화).
- **gh CLI 무효(GraphQL 403·토큰 무효)·guard 훅** → 모든 역할이 MCP로 우회(오늘 journal friction 8회+). harness 후보: 지침의 `gh` 예시를 MCP 기준으로.
- 취소된 첫 run이 같은 sha에 gates=failure를 남김(friction 5회+). 후보 유지.
- builder가 harness-change PR에 experiments 기록을 빠뜨림(#269 CHANGES). 후보: builder.md에 명시.
- 머지된 브랜치 삭제 도구 없음(friction 3회) — #105 관련.
- 이전 후보 유지: ARCHITECTURE.md 단일 줄 충돌, f) builder PR 소유 구분, h) CHANGES 2회 규칙 예외, k) 동시 webhook 잠금, gates quick 210~261초(목표 90초), gates tests 20~25분(reviewer 대기).
- NEEDS_HUMAN: NH-3 open. 리포 상호작용 제한 2027-04-23 만료.
## 진행 중 실험 (Auditor 소유, 그대로 유지)
- 001 builder 자가 언블록 (#55 머지 PR #57, 10-25 03:50Z). 측정창: 머지 후 14일. 성공 기준: builder no_work ≤10%(기준 24%), 처리량 80% 이상 유지.
- 009 planner run_on_merge (#130 PR #131 머지 51686a6, 10-27 12:38Z). 기록: harness/experiments.
- 015 gates 시간 상한 50분 (#199 PR #200 머지 6508d38, 10-27 18:28Z). 기록: harness/experiments.
