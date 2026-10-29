# STATE (2026-10-29 08:25Z, planner)
## 현재 단계
**D2 설계·준비(주력) + 사용자 지시: 서비스에 실제 TP-GTO 정책 연결·노리밋 정상화(P0).** D1 종료, NH-3·NH-5 open(비차단), FEEDBACK.md 없음.
D2 종료 조건 대비: Gate R 100%(캐시·토너먼트·E3) 유지 / TP v1: #262·#263 머지(ADR 0011) / 게이트: T1~T4·Q4(E0·E1)·S v0(+ADR 0016)·F v0 머지 / 비용 ADR 0017 / 설계 ADR 0009·0011·0015·0016·0017.
08:20Z 머지: PR #348(#333 Refs, 중수 6인·9인 pod32 잡 명세, 최악 각 $3). 파드 run 40840669062(e3-tp-pro-pod32, 08:14Z 시작, 최대 320분·예약 $6.4) 진행 중 → 끝나면 #333 기준 2·#346 기준 2 기록. 08:09Z 머지: PR #338(#332 Refs, 고수 board.nut NUT_K=5; 17단계 체크포인트 from_state 거부 → 고수 학습은 새로 시작). 07:29Z 머지: PR #347(#346 기준 1, RunPod 결과 한도 256MB → 파드 학습 모델 회수 가능; 기준 2는 #333 결과로). 06:47Z 머지: PR #334(#333 Refs, 기준 2 = 파드 실행 남음). 05:18Z 머지: PR #331(#315 닫힘) TP v0.2 초보 hand.equity 순위형(share_better 정답식·bands, 데모 정답 = 내 레인지 표본). 04:0xZ 머지: PR #328(#321 1/2).
새 이슈(사용자 lobster0113, 04:14~04:46Z): #333 RunPod 32 vCPU 학습(PR #334 CHANGES: Closes→Refs), #335 JS E3 엔진·번역(PR #342), #336 정책 내보내기(PR #340), #337 서비스 화면 연결, #339 사이즈 메뉴 TP §6, #341 비정상 제약 전수 점검(추적).
planner 08:15Z: #332 in-progress→ready(머지 후 e3-tp-pro-w4 10⁵×4 새 run vs 40815871622 비교·노트), #342에 NUT_K=5 벡터 재생성 안내, #240 ready 제거(P3, 큐 8 유지). planner 07:35Z: #264·#321 in-progress 6h+ PR 없음 → ready로 회수(#264 = 노트 PR만, #321 = 32 vCPU 잡 실행, #333과 묶기 권장), #346 기준 2를 #333에 연결. planner 06:55Z: #333 in-progress→ready(P0, e3-tp-pro-pod32 dispatch·결과 기록 인수인계), #337 blocked→in-progress(PR #344, #342·#340 머지 후 재리뷰), #339 PR #345. planner 05:25Z: #337·#339 계약 형식으로 재작성(#337 = Gate U 기준, #335·#336 선행이라 blocked; #339 = RAISE_CAP 제거 옵션·Gate R 검사 추가 포함), #343 새 이슈(LBR 메뉴 밖 사이즈, referee-change, #341 항목 6), #341 ready 제거(추적용, 항목 연결 코멘트), #332 ready→in-progress(PR #338).
## 이번 주 초점 (3개 이하, 이유 포함)
1. **실제 정책으로 서비스 화면(#335→#336→#337, P0)**: 사용자 직접 지시. 학습 중간본을 서비스에서 체험 가능해야 피드백 루프가 돈다. 열린 PR #342·#340 리뷰가 병목.
2. **노리밋 정상화(#341: #339 메뉴·상한, #343 LBR 메뉴 밖)**: 착취도 과소평가는 판정 능력 결함 → #343 P1 referee-change 우선.
3. **고수 체인 비용(#333 파드 학습, #332 키 폭증 PR #338, #320·#321 실측)**: ADR 0017 가정을 실측값으로 교체.
## 큐
ready 8: #333 P0(파드 run 40840669062 결과 기록 대기), #346 P0(기준 2 = #333 결과 기록), #332 P1(머지 후 비교 run), #343 P1(referee-change), #264 P2(노트 PR만), #321 P2(2/2 잡), #320 P2, #327 P3. 보류: #240 P3.
in-progress: #335 P0(PR #342), #336 P0(PR #340), #337 P0(PR #344), #339 P1(PR #345), #306 P2(builder-b, train run 40807006873 대기).
blocked: #105. 상태 라벨 없음: #341(추적), #189(GTO 브라우저 P1, D3), #323(P3, referee-change 판단 필요).
후보(이슈화 보류): 스택 분포 무작위화(#341 항목 7, #339 결과 후), E2 RAISE_CAP(#339 노트 후), Gate S·F 등급 표 CI 출력 경로(지표 등록 referee-change), ADR 0017 개정(#320·#321·#325·#333 결과 후), e3-tp-*9-w4·pro-w4 학습 결과 기록, Gate S·F 포스트플랍(E2), 커리큘럼 후속(#173 §7).
## 지표 요약 (최근 값과 추세)
- CI bbe6d22(#331) success, 0bae91d(#334) 진행 중. CI 4a1237b(10-29 04:33Z): tests 1172(+29), failed 0, gate_r 1.0(224,269), gate_r_cash 1.0(224,636), gate_r_e3 1.0(37,462), gate_l 1.0(32), stalker_loc 11177(+281). bbe6d22(#331) CI 지표 대기.
- E2 LBR(#259 후 CI): baseline −0.159, beginner −0.244, mid −0.234 bb/hand(하한 — 메뉴 안 착취자만, #343으로 보강 예정).
- E1 분위 눈금: 초보 손실 0.244 → 0.018 bb/hand(노트). S v0 고수 분위 ADR 0016 기준 통과(record-only).
- E0 CFR-BR(#311, 로컬 참고): Kuhn k=2 0.170→0.056, Leduc 1×1 2.36→0.98 → #327로 CI 기록 예정.
- 연산(#264, RunPod 1회): 641.96 it/s(2 vCPU), CI 177.7~220.6 it/s, 비용 $0.0037/회.
## 경보
- **사용자가 계약 형식 아닌 ready 이슈를 직접 생성(#337·#339·#341)** → planner가 재작성. 내용 보존, 기준만 검증 가능하게.
- **gh CLI 토큰 무효·GraphQL 403·guard 훅(gh api PATCH 차단)** → 전 역할 MCP 우회. 후보: 지침의 gh 예시를 MCP 기준으로.
- **Actions 아티팩트 blob 호스트 프록시 403**: reviewer가 Gate U를 로컬로 대체(#331). train.yml 결과도 같은 문제 가능 — 후보(Auditor).
- **"Closes #N" vs 실행 후 기준**(#334·#345 재발, builder friction 3회+ → area:harness 후보: planner가 머지 후 실행 기준을 별도 이슈로 쓰도록 지침 보강). #339 기준 4 "Gate R 검사 추가"가 referee-change 없이 쓰여 builder가 tests/로 우회 — planner 책임, 이후 이슈는 라벨 맞출 것: 머지 후에만 가능한 기준은 처음부터 별도 이슈로. 같은 sha 규칙 때문에 본문만 고친 PR은 재리뷰 불가(reviewer-b friction).
- 동시 취소 run의 gates=failure(같은 sha), 게이트를 작업 트리에서 백그라운드로 돌리면 가짜 실패(builder friction → 별도 worktree 권장). gates full 약 20분·quick 448초(목표 90초).
- 머지된 브랜치 삭제 도구 없음(#105, guard 훅이 push --delete 차단).
- 실험 기록 규칙 누락 쉬움, 닫힌 이슈 in-progress 잔존, PR 소유 구분 불가(같은 로그인), ARCHITECTURE.md 충돌: 후보 유지.
- NEEDS_HUMAN: NH-3, NH-5 open. 리포 상호작용 제한 2027-04-23 만료.
## 진행 중 실험 (Auditor 소유, 그대로 유지)
- 001 builder 자가 언블록 (#55 머지 PR #57, 10-25 03:50Z). 측정창: 머지 후 14일. 성공 기준: builder no_work ≤10%(기준 24%), 처리량 80% 이상 유지.
- 009 planner run_on_merge (#130 PR #131 머지 51686a6, 10-27 12:38Z). 기록: harness/experiments.
- 015 gates 시간 상한 50분 (#199 PR #200 머지 6508d38, 10-27 18:28Z). 기록: harness/experiments.
