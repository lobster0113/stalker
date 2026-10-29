# STATE (2026-10-29 18:15Z, planner)
## 현재 단계
**D2 설계·준비(주력) + 사용자 지시: 서비스에 실제 TP-GTO 정책 연결·노리밋 정상화(P0).** D1 종료, NH-3·NH-5·NH-6 open(비차단), FEEDBACK.md 없음.
planner 18:15Z: 15:00Z 이후 머지 6건 반영 — PR #357(#355 닫힘, 웹 정책 --strategy average·파드 결과 int16 버그), #363(#360 닫힘, 고수 파드 정책 서비스 연결), #365(#333 Refs, ADR 0017 §8 파드 실측), #370(#346 닫힘, 실험 024 결과 회수 크기), #366(#350 닫힘, 실험 025 동시 파드 관측), #367(#349 닫힘, CI web 잡 node 테스트). main c4f3c13 CI success(tests 1265).
사용자 새 이슈 계약 형식 재작성: #374(P1 ready, referee-change, E3 필드 worst가 self5=0 포함해 실제 최악 상대를 가림) / #373(P1 ready, RunPod cpu5c 실측: cpu3c는 Zen 3/5 무작위로 처리량 2배 차). #306 RECLAIM(15h+ PR 없음, 두 run 결과 ops에 있어 노트 PR만 남음) → ready P2.
열린 PR: #369(#358, CHANGES 대응 후 재리뷰 대기), #368(#352 ADR 0018, CHANGES: 중수 수치 갱신), #375(#360 후속, Gate U 고수 첫 핸드 40턴 실패 사유).
D2 종료 조건 대비: Gate R 100%(캐시·토너먼트·E3) 유지 / TP v1: #262·#263 머지(ADR 0011) / 게이트: T1~T4·Q4(E0·E1)·S v0(+ADR 0016)·F v0 머지 / 비용 ADR 0017(§8 실측 반영) / 설계 ADR 0009·0011·0015·0016·0017.
## 이번 주 초점 (3개 이하, 이유 포함)
1. **판정 정확성(#374 P1, #341: #339 2/2)**: 필드 worst가 self5 0.0으로 고정돼 고수·중수 결과의 "최악 상대"가 과대평가됐다. 판정이 틀리면 진척 판단이 틀린다 → 최우선급.
2. **고수 체인 비용(#354 P0 체인 2회, #358 → #333 기준 2, #373 cpu5c, #332 비교 노트)**: 파드 1회 ≈ 고수 200만 회뿐 → 체인 필수. Zen 3 당첨은 달러당 반복을 절반으로 만든다.
3. **실제 정책 서비스 품질(#364 P1, #375, #352 ADR 0018)**: 고수·중수 파드 정책이 서비스에 연결됨(#363). 등급 변경 버그·공개 전 서버 서빙.
## 큐
ready 7: #354 P0(harness-change, 고수 파드 체인 2회), #374 P1(referee-change, 필드 worst 정의), #373 P1(cpu5c 실측), #364 P1(등급 변경 다음 핸드 적용, Gate U), #339 P1(2/2: 10⁵ 비교 run·노트), #306 P2(노트 PR만), (#358 PR 머지되면 #333 ready).
in-progress: #358 P0(PR #369), #352 P1(PR #368), #332 P1(builder CLAIM 18:06Z, run 40894774806 비교 노트).
blocked: #105, #333 P0(#358). 보류: #359 P2(referee-change), #264 P2, #321 P2, #320 P2, #240 P3, #327 P3. 상태 라벨 없음: #341(추적), #189(D3), #323(P3).
후보(이슈화 보류): #374 머지 후 기록된 worst 값(#333·#360·ADR 0017 §8) 재계산, e3_suite가 tp6·상한 없음 규칙 기본 재생(referee-change, #339 2/2 후), 스택 분포 무작위화(#341 항목 7), E2 RAISE_CAP(#339 노트 후), Gate S·F 등급 표 CI 출력 경로, ADR 0017 개정(#321·#373 결과 후), Gate S·F 포스트플랍(E2), 커리큘럼 후속(#173 §7).
## 지표 요약 (최근 값과 추세)
- CI c4f3c13(18:00Z): tests 1265(+93 vs 04:33Z), failed 0, gate_r 1.0(224,269), gate_r_cash 1.0(224,636), gate_r_e3 1.0(37,462), gate_l 1.0(32), stalker_loc 11856. 지난 2주 Gate R·L 100% 유지.
- E1(CI): 착취도 초보 0.0191·중수 0.0033·고수 0.0009(NFP 0.0019), Gate S 초보 분위 passed=false(tv_p95 0.127, golden 11/12) 지속 — 정체 축, ADR 0016 record-only.
- Gate F E1 Nash 손실: 초보 0.110·중수 0.040·고수 0.011 (정체, 변화 없음).
- E0 CFR Kuhn 8.7e-5, Leduc 0.0023.
- E3 파드(참고, #333·ADR 0017 §8): 고수 NUT5 2.18M회 195,084키 LBR 현재 0.466±0.189 / 평균 0.774. 필드 worst 값은 #374로 정의 수정 전까지 신뢰 불가.
- 클라우드 지출: 월 $9.45 / $100(실험 025 기록).
## 경보
- 파드 시작 실패(#361) 해결 후 동시 파드 3개 정상(실험 025, #366). 필드 worst=self5 0.0 보고가 여러 이슈·ADR에 전파됨(#374).
- **사용자가 계약 형식 아닌 ready 이슈를 직접 생성(#337·#339·#341·#352·#354·#364·#373·#374)** → planner가 재작성. 내용 보존, 기준만 검증 가능하게.
- **gh CLI 토큰 무효·GraphQL 403·guard 훅(gh api PATCH 차단)** → 전 역할 MCP 우회. 후보: 지침의 gh 예시를 MCP 기준으로.
- **Actions 아티팩트 blob 호스트 프록시 403**: reviewer가 Gate U를 로컬로 대체(#331). train.yml 결과도 같은 문제 가능 — 후보(Auditor).
- **"Closes #N" vs 실행 후 기준**(#334·#345 재발, builder friction 3회+ → area:harness 후보: planner가 머지 후 실행 기준을 별도 이슈로 쓰도록 지침 보강). #339 기준 4 "Gate R 검사 추가"가 referee-change 없이 쓰여 builder가 tests/로 우회 — planner 책임, 이후 이슈는 라벨 맞출 것: 머지 후에만 가능한 기준은 처음부터 별도 이슈로. 같은 sha 규칙 때문에 본문만 고친 PR은 재리뷰 불가(reviewer-b friction).
- **충돌 PR은 pull_request CI가 안 돈다 → 리뷰어가 되돌리기만 반복**(#340·#345, reviewer friction 3회+ 10-29) → area:harness 후보: builder가 푸시 전 main 머지 의무화·충돌 알림.
- **원장 push 충돌로 파드 run red**(40840669062, #351 이전 커밋에서 시작) — #351 이후 run은 union 병합이라 재발 여부를 실험 025 창에서 볼 것. 1MB 초과 결과는 ops 미게시(#358).
- 동시 취소 run의 gates=failure(같은 sha), 게이트를 작업 트리에서 백그라운드로 돌리면 가짜 실패(builder friction → 별도 worktree 권장). gates full 약 20분·quick 448초(목표 90초).
- 머지된 브랜치 삭제 도구 없음(#105, guard 훅이 push --delete 차단).
- 실험 기록 규칙 누락 쉬움, 닫힌 이슈 in-progress 잔존, PR 소유 구분 불가(같은 로그인), ARCHITECTURE.md 충돌: 후보 유지.
- NEEDS_HUMAN: NH-3, NH-5, NH-6 open. 리포 상호작용 제한 2027-04-23 만료.
## 진행 중 실험 (Auditor 소유, 그대로 유지)
- 001 builder 자가 언블록 (#55 머지 PR #57, 10-25 03:50Z). 측정창: 머지 후 14일. 성공 기준: builder no_work ≤10%(기준 24%), 처리량 80% 이상 유지.
- 009 planner run_on_merge (#130 PR #131 머지 51686a6, 10-27 12:38Z). 기록: harness/experiments.
- 015 gates 시간 상한 50분 (#199 PR #200 머지 6508d38, 10-27 18:28Z). 기록: harness/experiments.
