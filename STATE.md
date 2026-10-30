# STATE (2026-10-30 04:45Z, planner)
## 현재 단계
**D2 설계·준비(주력) + 소유자 방향 전환(10-30): 실전 게임 학습. ADR 0019(제안, PR #392 머지 742daae) 순서: A real 메뉴(#382·#386 완료·#387) → B1 드로우·블로커(필수)·B2·B3(#389) ∥ S 좌석별 스택(#383) → C 결합 key(#400, 전체 체인은 여기서만) → D 2–5인(#384) → E 토너먼트(#385).** 예산 중간값 약 $1,600 → NH-9(월 상한 상향) open. D1 종료, NH-3·5·6·7·9 open(비차단), FEEDBACK.md 없음.
planner 00:10Z: #390 닫힘 반영(in-progress 제거). ADR 0019 §3·§8 분해: #395 B1-1 TP hand.block·무늬 인식 명세(ready, referee-change), #398 B1-2 key(blocked #395), #396 S1 엔진 스택·사이드팟+Gate R(ready, referee-change), #399 S2 유효 스택·SPR key(blocked #396, referee-change), #397 서비스 임시 정책 표시(ready), #400 C 결합 key(blocked), #401 launcher flavor 대체·재시도(blocked #373, harness-change). #383·#389 추적용(ready 뗌), #384 blocked(#400, 인원별 정책 → 한 정책+칸 예약), #385 선행 #400.
planner 00:31Z: PR #402 머지(6f47da4) → #386 닫힘, ready·in-progress 라벨 제거. 새 ready #405(E3 평균 전략 레인지, #403 발견)·#406(예산 상한 $300, NH-9 승인, harness-change).
main 6f47da4 CI 진행 중. 열린 PR: #394(#373 cpu5c), #403(#393 벡터 CFR), #404(#395 블로커 조사). in-progress: #373, #393.
planner 04:15Z: 머지 반영 #394(#373 잡 추가, run·노트는 머지 후 기준 — in-progress 유지), #404(#395 조사), #403(#393 닫힘). 외부 설계 리뷰 유입 #410–#420(소유자 세션, 계약 형식, 10개 중 9개 ready) → 큐 상한 맞춤: #410·#414(선행 #359)·#416(선행 #398)·#411(선행 PR #407) blocked, #419·#306 ready 뗌(보류). #409(프리플랍 프로브)는 #413 기준 1과 겹침 — builder는 #413에서 함께 처리 권장.
planner 04:22Z: PR #421 머지(533e775) → #420 닫힘(ADR 0019 R0·R1·C 착수 조건 반영). 큐 변동 없음(ready 8).
planner 04:45Z: PR #422 머지(8eec9bf) → #412 닫힘(raise-to 정의·짧은 올인 비재오픈·Gate R 엣지), ready·in-progress 제거. 후속 의존 없음. ready 7.
main 8eec9bf CI 진행 중. 열린 PR: #407(#405, 충돌→builder main 머지 대기), #408(#395, CHANGES 해결 fa70faf), #423(#391).

## 이번 주 초점 (3개 이하, 이유 포함)
1. **B1 드로우·블로커(#395 PR #408→#398)**: 소유자 필수 항목, 결합 key 선행.
2. **S 좌석별 스택(#396→#399)** (합법 액션 경계 #412 완료): 소유자 "크리티컬", B와 독립.
3. **단계 C 착수 조건(ADR 0019 R0·R1 머지, PR #421)**: 평가 보강 #413(프리플랍 프로브·RL-BR)이 #391 림프 누수를 잡아야 진척 판단 가능 → 심판 능력 우선.
## 큐
ready 7(+in-progress): #387 P1, #396 P1, #406 P1, #413 P1(referee-change), #417 P1, #397 P2, #415 P2, #418 P2. in-progress: #373(머지 후 run·노트), #391, #395, #405.
blocked: #398(#395), #399(#396), #400(B·S), #401(#373), #384·#385(#400), #410·#414(#359), #411(PR #407), #416(#398), #105. 추적: #383, #389, #341. 보류: #419 P2, #306 P2, #359 P2, #264 P2, #321 P2, #320 P2, #409 P2, #240 P3, #327 P3. 상태 라벨 없음: #189(D3), #323(P3).
후보(선행 머지 후 이슈화): B2·B3·B1 웹 미러·B1 측정 노트(#398 후), S 웹 미러·스택 비율 사이즈·S 측정 노트(#396 후), ADR 0018 서버 추론(NH-7 후), #418 워크플로 저장(harness-change 분리), Gate S·F 등급 표 CI 출력.
## 지표 요약 (최근 값과 추세)
- CI d1431a1(02:17Z): tests 1307(+42 vs c4f3c13), stalker_loc 12493; c4f3c13: tests 1265, failed 0, gate_r 1.0(224,269), gate_r_cash 1.0(224,636), gate_r_e3 1.0(37,462), gate_l 1.0(32), stalker_loc 11856. 지난 2주 Gate R·L 100% 유지.
- E1(CI): 착취도 초보 0.0191·중수 0.0033·고수 0.0009(NFP 0.0019), Gate S 초보 분위 passed=false(tv_p95 0.127, golden 11/12) 지속 — 정체 축, ADR 0016 record-only.
- Gate F E1 Nash 손실: 초보 0.110·중수 0.040·고수 0.011 (정체, 변화 없음).
- E0 CFR Kuhn 8.7e-5, Leduc 0.0023.
- E3 파드(참고, #333·ADR 0017 §8): 고수 NUT5 2.18M회 195,084키 LBR 현재 0.466±0.189 / 평균 0.774. 필드 worst 값은 #374(머지) 이전 기록이라 재계산 전까지 신뢰 불가.
- 클라우드 지출: 월 $9.45 / $100(실험 025 기록).
## 경보
- **#382 머지는 TP.md §6 변경 → 학습·채점은 real 메뉴 기준.** 웹 라벨(#386) 머지로 메뉴 일치, v1 정책(서비스)은 여전히 임시본(#397 표시).
- **사용자 이슈 대량 유입(#383~#391, 1시간에 8건)** — 영역·종류 라벨 없음, 일부 범위 밖·선행 없음, 크기 초과. planner가 라벨만 보강, 내용은 소유자 원문 유지.
- builder-b #384 작업이 컨테이너 종료로 유실(푸시 전) → 긴 작업은 중간 WIP 푸시 권장. 원인: PreToolUse guard 훅이 상대 경로라 `cd web/e2e` 뒤 모든 Bash 실패 → area:harness 후보(`$CLAUDE_PROJECT_DIR` 절대 경로, Auditor).
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
- **ready 큐 범람**: 소유자 세션이 외부 리뷰 RFC 10건을 한 번에 ready로 올림 → planner가 선행 미충족분 blocked. 선행이 열린 이슈에 ready를 붙이지 않도록 대화 세션에 권고(후보).
- NEEDS_HUMAN: NH-3, NH-5, NH-6, NH-7 open (NH-8·NH-9 resolved). 리포 상호작용 제한 2027-04-23 만료.
## 진행 중 실험 (Auditor 소유, 그대로 유지)
- 001 builder 자가 언블록 (#55 머지 PR #57, 10-25 03:50Z). 측정창: 머지 후 14일. 성공 기준: builder no_work ≤10%(기준 24%), 처리량 80% 이상 유지.
- 009 planner run_on_merge (#130 PR #131 머지 51686a6, 10-27 12:38Z). 기록: harness/experiments.
- 015 gates 시간 상한 50분 (#199 PR #200 머지 6508d38, 10-27 18:28Z). 기록: harness/experiments.
