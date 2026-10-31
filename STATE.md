# STATE (2026-10-31 10:00Z, planner)
## 현재 단계
**D2 설계·준비(주력) + 소유자 방향 전환(10-30): 실전 게임 학습. ADR 0019(제안, PR #392 머지 742daae) 순서: A real 메뉴(#382·#386 완료·#387) → B1 드로우·블로커(필수)·B2·B3(#389) ∥ S 좌석별 스택(#383) → C 결합 key(#400, 전체 체인은 여기서만) → D 2–5인(#384) → E 토너먼트(#385).** 예산 중간값 약 $1,600 → NH-9(월 상한 상향) open. D1 종료, NH-3·5·6·7·9 open(비차단), FEEDBACK.md 없음.
planner 10-30 요약: #405·#430·#396·#417·#426·#441·#398·#454·#440 닫힘, #411→#451·#446 분해, B2 #460·B3 #461·b1 비용 2차 #462 생성, #391 blocked(RFC-03 추적).
planner 10-31 00:55Z: #456(#447) 머지 → #447 닫힘(라벨 정리). BLAS→고정 순서 합, regret_sha256 결과 기록. **이전 CI run과 시드별 비트 비교 불가**(시드 평균 비교 또는 기준 재실행). 2×10⁴ 비교 CI 잡은 #463(area:harness, harness-change 부여는 Auditor 판단). 후보: E2·referee(e2 exploiter·e3 preflop_probe, 보호) `sigma @ vals` 동일 패턴.
planner 02:35Z: #467 머지(2e8711f, Refs) → #413 기준 3(옛 챔피언 필드 v2) 충족, 남은 건 기준 2(RL-BR)만, in-progress 해제. **main CI red 확인(ab1d186·51e7849 연속 gates(tests) 실패, b1 지문 digest 불일치) → P0 #469 생성.** 후속 후보: pro 정책 보관(LFS/작은 export 결정), real 메뉴 챔피언 v3.
planner 04:50Z: #470(#460 B2) 머지 c3c442c → #460 닫힘(라벨 정리). b1·b2 비교 run이 ops에 0건 → #472(P1, train.yml로 b1-w4·b2-w4 같은 iters·seeds, 노트 기입) 생성. **main CI 64ddebf success**(#469 지문 실패는 러너 의존 간헐, PR #471 열림).
planner 04:55Z: #471(#469 P0) 머지 52e310a → #469 닫힘(in-progress 제거). b1 지문은 정수 b1_code만 해시, PR CI run 41167921228 green. main push CI 41170058811 진행 중 — 다음 실행에서 결과 확인.
planner 07:40Z: #473(#461 B3) 머지 8f6ea02·#474(#413 RL-BR) 머지 07bb388 → #461·#413 닫힘(라벨 정리). 52e310a push CI success(#469 해결 확인). B3 비교 run #475(P1) 생성, #400 선행은 #472·#475만 남음(코멘트). 8f6ea02·07bb388 CI 진행 중.
planner 10:00Z: #449(#444 딜 시드) 머지 c649c87 → #444 닫힘(라벨 정리). c649c87 push CI 진행 중. ready 4(+in-progress 2), 새 이슈 없음.
열린 PR(10:00Z): #476(#465, 리뷰 대기), #466(#373, MERGE 판정 후 머지 거부 → 미머지, 재시도 규칙 없음).

## 이번 주 초점 (3개 이하, 이유 포함)
1. **평가 신뢰(#463)**: P0 #469 해결(#471, main green), RL-BR #413 머지(#474). 남은 건 러너 간 결정성 CI 잡과 RL-BR 수치를 E3 보고에 쓰는 것.
2. **B 단계 측정(#472·#475)**: S·B1·B2·B3 key 정의 모두 머지. CI 비교 수치 0건 → C(#400) 선행은 이 두 측정뿐. 비용 2차 #462는 P2.
3. **단계 C 레인지 결정(#446)·#391 추적**: C 착수 조건(ADR 0019 §3.4).
## 큐
ready: #446 P1(C 레인지 A/B), #472 P1(b1·b2 비교 run), #475 P1(b3 비교 run), #462 P2(b1 비용 2차), #465 P1(서비스, 소유자 대화). in-progress: #465(PR #476), #373(PR #466). 상태 라벨 없음: #463(harness).
blocked: #391(RFC-03 추적), #406·#427(소유자 보류, 예산), #387(기준 3, 수렴 real 정책), #400(#472·#475 측정), #401(#373), #384·#385(#400), #410(#359), #416(#389 B 미완), #105. 추적: #383, #389, #341. 보류: #448·#429·#418·#415·#397·#419·#306·#359·#264·#321·#320·#409 P2, #240·#327 P3. 상태 라벨 없음: #189(D3), #323(P3).
후보(선행 머지 후 이슈화): #391 L4·L5 소규모 재학습+preflop_ev 핸드 그룹×포지션 표 CI 잡, #441 결함 파일 CI 재생성·검증(정책 재학습 시 갱신, #450 후속), S 측정 run 노트(B1·B2 #472, B3 #475), RL-BR CI 지표(harness-change), 웹 key 미러(C에서), S 웹 미러·스택 비율 사이즈·S 측정 노트(#396 후), ADR 0018 서버 추론(NH-7 후), #418 워크플로 저장(harness-change 분리), Gate S·F 등급 표 CI 출력, 프리플랍 프로브 CI 지표 `e3_preflop_probe_leaks`(harness-change, 110칸 약 75분/3코어 → 등록된 작은 칸 집합 후보, PR #428 후속).
## 지표 요약 (최근 값과 추세)
- CI fe59189(18:05Z): tests 1465, failed 0, gate_r·cash·e3 1.0(e3 116,238), gate_l 1.0(32), stalker_loc 14650 (오늘 +80 tests vs 2dbe609).
- CI 2dbe609(11:06Z): tests 1385, failed 0, gate_r 1.0, gate_r_e3 1.0(116,238, 불균등 스택 재생 추가), gate_l 1.0(32), stalker_loc 13411.
- CI d1431a1(02:17Z): tests 1307(+42 vs c4f3c13), stalker_loc 12493; c4f3c13: tests 1265, failed 0, gate_r 1.0(224,269), gate_r_cash 1.0(224,636), gate_r_e3 1.0(37,462), gate_l 1.0(32), stalker_loc 11856. 지난 2주 Gate R·L 100% 유지.
- E1(CI): 착취도 초보 0.0191·중수 0.0033·고수 0.0009(NFP 0.0019), Gate S 초보 분위 passed=false(tv_p95 0.127, golden 11/12) 지속 — 정체 축, ADR 0016 record-only.
- Gate F E1 Nash 손실: 초보 0.110·중수 0.040·고수 0.011 (정체, 변화 없음).
- E0 CFR Kuhn 8.7e-5, Leduc 0.0023.
- E3 파드(참고, #333·ADR 0017 §8): 고수 NUT5 2.18M회 195,084키 LBR 현재 0.466±0.189 / 평균 0.774. 필드 worst 값은 #374(머지) 이전 기록이라 재계산 전까지 신뢰 불가.
- 클라우드 지출: 월 $9.45 / $100(실험 025 기록).
## 경보
- main CI red(ab1d186·51e7849) → P0 #469 PR #471 머지(52e310a, 정수 코드만 해시). 52e310a push CI 결과 확인 대기. 교훈: float 원바이트 digest 고정 금지; #459 머지 시 CI 확인 누락 의심(Auditor).
- **PR #466 MERGE 판정 후 squash 머지가 세션 권한 분류기에 거부**(reviewer-b 01:57Z) → 같은 sha 규칙으로 이후 실행이 모두 skip(reviewer-b friction 5회+, 10-31) → area:harness 후보(같은 sha MERGE 판정의 머지 재시도 규칙, Auditor).
- **10-30 오후 ARCHITECTURE.md·index.html 충돌로 MERGE 판정 후 머지 실패 2건(#449·#443), CHANGES 누적(#423 2회)** — 충돌 PR은 CI가 없어 reviewer는 CHANGES만 가능(reviewer friction 5회+, area:harness 후보 유지, Auditor). 스택 PR(#452가 #443 포함) → 빈 PR 발생.
- 머지 후에만 가능한 CI 비교를 수용 기준에 넣은 이슈(#447 기준 1: 2×10⁴ CI 비교) → 비하네스 PR은 CI 잡 추가 불가(reviewer-b friction). planner: 새 이슈(#460·#461)는 잡 정의까지만, 수치는 별도 이슈.
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
- **ARCHITECTURE.md 동시 머지 충돌 반복**(#431·#432·#434·#437·#438, 10-30 reviewer·builder friction 5회+) → 충돌 PR에 CI 없음 → area:harness 후보(문서 색인 분할 또는 builder 푸시 전 mergeability 확인, Auditor).
- **ready 큐 범람**: 소유자 세션이 외부 리뷰 RFC 10건을 한 번에 ready로 올림 → planner가 선행 미충족분 blocked. 선행이 열린 이슈에 ready를 붙이지 않도록 대화 세션에 권고(후보).
- NEEDS_HUMAN: NH-3, NH-5, NH-6, NH-7 open (NH-8·NH-9 resolved). 리포 상호작용 제한 2027-04-23 만료.
## 진행 중 실험 (Auditor 소유, 그대로 유지)
- 001 builder 자가 언블록 (#55 머지 PR #57, 10-25 03:50Z). 측정창: 머지 후 14일. 성공 기준: builder no_work ≤10%(기준 24%), 처리량 80% 이상 유지.
- 009 planner run_on_merge (#130 PR #131 머지 51686a6, 10-27 12:38Z). 기록: harness/experiments.
- 015 gates 시간 상한 50분 (#199 PR #200 머지 6508d38, 10-27 18:28Z). 기록: harness/experiments.
