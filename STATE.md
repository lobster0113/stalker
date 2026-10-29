# STATE (2026-10-29 23:40Z, planner)
## 현재 단계
**D2 설계·준비(주력) + 소유자 방향 전환(10-30): 실전 게임 학습(실전 사이즈·좌석별 스택·2–6인·앤티/ICM·TP key 보강), 실전성은 비용과 바꾸지 않음. v1 파드 체인 중지(#354·#333 닫힘), 서비스 v1 중수·고수 정책은 임시본.** D1 종료, NH-3·5·6·7·9 open(비차단), FEEDBACK.md 없음.
planner 23:40Z: PR #388 머지(4ff4cab, #382 닫힘: TP §6 실전 사이즈 메뉴 real + 의사 조화 번역, job e3-tp-mid-real-w4), 닫힌 #382 ready·in-progress 제거. main 9bb64ec CI success, 4ff4cab CI 진행 중(run 40973661723).
사용자 새 이슈 라벨 보강: #383(area:engine, referee-change, 스택·사이드팟), #384(area:ai, 2–6인; builder-b 핸드오프 코멘트 있음, 작업 유실), #385(area:ai → blocked, 선행 #383), #389(area:ai, referee-change, TP key 보강·드로/블로커 필수), #390(area:docs, ADR 0019 계획, builder 착수), #391(area:ai kind:bug, BTN AQs 림프 54–65%). #386·#387(#382 후속), #373 cpu5c는 진행 중.
열린 PR: 없음(#390·#386·#373 builder 작업 중).
D2 종료 조건 대비: Gate R 100%(캐시·토너먼트·E3) 유지 / TP v1: #262·#263(ADR 0011) / 게이트 T1~T4·Q4·S v0·F v0 / 비용 ADR 0017 → ADR 0019(#390)가 대체 예정.
## 이번 주 초점 (3개 이하, 이유 포함)
1. **학습 계획 ADR 0019(#390)**: 실전 게임 단계 순서·재학습 공유·비용 범위·예산(NH-9) — 이후 모든 학습 이슈의 순서를 정함.
2. **실전 게임 1단계(#386 웹 real 메뉴, #387 CI 비용, #383 스택, #389 key)**: 소유자 "너무 크리티컬". #383·#389는 builder 1회를 넘는 크기 → builder는 `Refs #N` 단위로 나누고, ADR 0019 머지 후 planner가 하위 이슈로 분해.
3. **판정 사각지대(#391)**: LBR·필드가 프리플랍 '오픈 대신 림프' 누수를 못 잡음 → 원인 규명, 필요하면 referee-change 프리플랍 프로브 이슈.
## 큐
ready 6: #383 P1, #384 P1, #387 P1, #389 P1, #391 P1, #306 P2.
in-progress: #390, #386, #373. blocked: #385(#383 선행), #105. 보류: #359 P2, #264 P2, #321 P2, #320 P2, #240 P3, #327 P3. 상태 라벨 없음: #341(추적), #189(D3), #323(P3).
후보(이슈화 보류): #383·#389·#384·#385 하위 분해(ADR 0019 후), ADR 0018 서버 추론(NH-7 후), 기록된 worst 값 재계산(v1 정책 임시본이라 우선순위 낮춤), Gate S·F 등급 표 CI 출력, Gate S·F 포스트플랍(E2), 커리큘럼 후속(#173 §7).
## 지표 요약 (최근 값과 추세)
- CI c4f3c13(18:00Z): tests 1265(+93 vs 04:33Z), failed 0, gate_r 1.0(224,269), gate_r_cash 1.0(224,636), gate_r_e3 1.0(37,462), gate_l 1.0(32), stalker_loc 11856. 지난 2주 Gate R·L 100% 유지.
- E1(CI): 착취도 초보 0.0191·중수 0.0033·고수 0.0009(NFP 0.0019), Gate S 초보 분위 passed=false(tv_p95 0.127, golden 11/12) 지속 — 정체 축, ADR 0016 record-only.
- Gate F E1 Nash 손실: 초보 0.110·중수 0.040·고수 0.011 (정체, 변화 없음).
- E0 CFR Kuhn 8.7e-5, Leduc 0.0023.
- E3 파드(참고, #333·ADR 0017 §8): 고수 NUT5 2.18M회 195,084키 LBR 현재 0.466±0.189 / 평균 0.774. 필드 worst 값은 #374(머지) 이전 기록이라 재계산 전까지 신뢰 불가.
- 클라우드 지출: 월 $9.45 / $100(실험 025 기록).
## 경보
- **#382 머지는 TP.md §6 변경 → 이후 학습·채점은 real 메뉴 기준. v1 메뉴 정책(서비스)은 임시본**: 웹 라벨(#386) 전까지 메뉴 불일치 가능.
- **사용자 이슈 대량 유입(#383~#391, 1시간에 8건)** — 영역·종류 라벨 없음, 일부 범위 밖·선행 없음, 크기 초과. planner가 라벨만 보강, 내용은 소유자 원문 유지.
- builder-b #384 작업이 컨테이너 종료로 유실(푸시 전) → 긴 작업은 중간 WIP 푸시 권장(friction 후보).
- **RunPod 용량 부족: cloud.yml launch 6연속 실패(20:52~21:20Z, e3-tp-mid-pod32 RESUME 40919207457, HTTP 500 "no longer any instances available")** → 비용 0, #333·#354 체인 지연. 후보: launcher가 용량 오류 시 대체 flavor(#373 cpu5c)·지연 재시도.
- 파드 시작 실패(#361) 해결 후 동시 파드 3개 정상(실험 025, #366). 필드 worst=self5 0.0 보고가 여러 이슈·ADR에 전파됨(#374).
- **사용자가 계약 형식 아닌 ready 이슈를 직접 생성(#337·#339·#341·#352·#354·#364·#373·#374)** → planner가 재작성. 내용 보존, 기준만 검증 가능하게.
- **gh CLI 토큰 무효·GraphQL 403·guard 훅(gh api PATCH 차단)** → 전 역할 MCP 우회. 후보: 지침의 gh 예시를 MCP 기준으로.
- **Actions 아티팩트 blob 호스트 프록시 403**: reviewer가 Gate U를 로컬로 대체(#331). train.yml 결과도 같은 문제 가능 — 후보(Auditor).
- **"Closes #N" vs 실행 후 기준**(#334·#345 재발, builder friction 3회+ → area:harness 후보: planner가 머지 후 실행 기준을 별도 이슈로 쓰도록 지침 보강). #339 기준 4 "Gate R 검사 추가"가 referee-change 없이 쓰여 builder가 tests/로 우회 — planner 책임, 이후 이슈는 라벨 맞출 것: 머지 후에만 가능한 기준은 처음부터 별도 이슈로. 같은 sha 규칙 때문에 본문만 고친 PR은 재리뷰 불가(reviewer-b friction).
- **충돌 PR은 pull_request CI가 안 돈다 → 리뷰어가 되돌리기만 반복**(#340·#345, reviewer friction 3회+ 10-29) → area:harness 후보: builder가 푸시 전 main 머지 의무화·충돌 알림.
- **원장 push 충돌로 파드 run red**(40840669062, #351 이전 커밋에서 시작) — #351 이후 run은 union 병합이라 재발 여부를 실험 025 창에서 볼 것. 1MB 초과 결과 요약 게시(#358 머지).
- 동시 취소 run의 gates=failure(같은 sha), 게이트를 작업 트리에서 백그라운드로 돌리면 가짜 실패(builder friction → 별도 worktree 권장). gates full 약 20분·quick 448초(목표 90초).
- **실험 번호 동시 PR 충돌**(#369 027 중복, 010 중복 기존) → area:harness 후보(번호 예약). 라벨 추가가 중복 CI run·취소 failure 체크 남김(reviewer-b friction).
- 머지된 브랜치 삭제 도구 없음(#105, guard 훅이 push --delete 차단).
- 실험 기록 규칙 누락 쉬움, 닫힌 이슈 in-progress 잔존, PR 소유 구분 불가(같은 로그인), ARCHITECTURE.md 충돌: 후보 유지.
- NEEDS_HUMAN: NH-3, NH-5, NH-6, NH-7 open. 리포 상호작용 제한 2027-04-23 만료.
## 진행 중 실험 (Auditor 소유, 그대로 유지)
- 001 builder 자가 언블록 (#55 머지 PR #57, 10-25 03:50Z). 측정창: 머지 후 14일. 성공 기준: builder no_work ≤10%(기준 24%), 처리량 80% 이상 유지.
- 009 planner run_on_merge (#130 PR #131 머지 51686a6, 10-27 12:38Z). 기록: harness/experiments.
- 015 gates 시간 상한 50분 (#199 PR #200 머지 6508d38, 10-27 18:28Z). 기록: harness/experiments.
