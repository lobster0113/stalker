# STATE (2026-11-07 22:40Z, planner)
## 현재 단계
**D2 설계·준비(주력) + 소유자 방향 전환(10-30): 실전 게임 학습. ADR 0019 순서: A real 메뉴(#382·#386 완료·#387) → B1·B2·B3(#389) ∥ S 좌석별 스택(#383) → C 결합 key c1(#400) → D 2–5인(#384) → E 토너먼트(#385).** D1 종료. NH-3·5·6·7·9·11 open(비차단). FEEDBACK.md 없음(11-01 19:10Z 확인).
planner 11-07 20:10Z: **PR #649(8989f99, #648 L4 에퀴티 ±1 이웃 측정) 17:41Z 머지·PR #650(81025aa, #634 AIVAT equity_value) 19:13Z 머지**(이슈 닫힘). #648 결론(로컬 참고): L4가 3·4·6인 플랍 균등 −6.2–10.7%p → 신규 **#652 P2**(tpgto.js L4 미러·ADR 0022). #634: variance_ratio 2인 1.298·6인 1.105(>1, 분산 감소 없음) → 후속은 2인 ≥2000딜 재측정 전제, 지금 이슈화 안 함. 필터 정책 LBR(아티팩트 ~12-03 만료 전) → 신규 **#653 P2**. PR #651(#628) CHANGES: web 잡 ECONNRESET 플레이크(코드 무관). main CI 81025aa success. ready 미착수 3(#652·#653·#641).
planner 11-07 21:10Z: **PR #651(0988090c, #628 train_jobs 요약 chunk_iters·lbr_hands 시드별) 머지**(builder-b web 플레이크 재실행 뒤) → #628 ready·in-progress 정리(MCP). 신규 **#654 P2**(백오프 근사 품질: leave-one-out L1–L4 행 대 정확 행 TV, 균등 대비; #652 범위 밖 보완). main CI 0988090c 진행 중. ready 미착수 3(#653·#654·#641), in-progress #652.
planner 11-07 22:40Z: **PR #655(9a28d6bf, #652 tpgto.js L4 에퀴티 ±1 이웃 미러·ADR 0022) 22:31Z 머지** → #652 ready·in-progress 정리(MCP). L4 뒤 c1 mid-6 플랍 균등 13.7%(#648 로컬) 대 레거시 35.6% → 신규 **#656 P2**(mid-6 교체 재판단, 시드 2개, 아티팩트 ~12-03 만료 전). main CI d0be4f5 진행 중. ready 미착수 3(#654·#656·#641), in-progress #653.
## 이번 주 초점 (3개 이하, 이유 포함)
1. **D 2–5인(#384)**: 평가기(#534)·인원별 값(#542)·시드 분산(#548·#559) → 합격선 ADR 0020 머지(#564) → #572 판정기 머지(c1 2–6인 pass) → #576 기록 연결 머지 → #581 ADR 0021 머지(mixn c1 한 정책) → #583 웹 c1 key 미러 머지 → #585 인원별 내보내기 머지 → #588 CI 내보내기 머지 → #592 시드 M4·문턱 선택 머지 → #596 인원별 문턱·ops 정책 경로 머지 → #601 재-export 실측 머지(전 인원 상한 안) → #604 2–5인 반입·c1 키 라우팅 머지(프리플랍만) → #606 b1 칸 JS 이식 머지 → #608 포스트플랍 c1 키 머지 → #610·#611·#615 머지 → #618 ADR 0022 머지(런타임 거친 키 백오프) → #624 실측 머지(#629: 다인 플랍은 커버리지 탓) → #623 페이지 백오프 머지(#633) → #635 머지(#636: mid-6 교체 보류) → #631 머지(#639: 2인 mv=5 상한 안) → #638 머지(#642: 꼬리 키, 자리 묶음 L3 추천) → #644 머지(#646: np.empty 버그) → #645 머지(#647: L3 3·6인 −8–14%p) → #640 머지(#643: 2인 mv=5 반입) → #648 머지(#649: L4 3·4·6인 −6–11%p) → #652 머지(#655: L4 페이지 미러) → **#653 걸러 낸 정책 LBR ∥ #654 근사 행 품질 ∥ #656 mid-6 재판단**. 소유자가 크리티컬하다고 한 short-handed.
2. **C 고수 체인 비용(NH-11 (a))**: #479 완료(PR #603) — 10⁵회에서도 b2가 b1과 구별 안 됨 → c1 키 집합 유지, b2 추가 안 함. 다음 C 재측정 때 #527 it_ratio로 CPU 맞춘 배수 보고.
3. **페르소나 목표 타당성(#641)**: #627 머지(PR #637) — 인간 c-bet 헤즈업 SRP 53.0·3bet 62.0·멀티웨이 29.3, TAG 65±6 밖 → 목표 변경 추천. 먼저 시뮬레이터 페르소나를 같은 4칸으로 재고(#641), 그다음 PRESETS_V2 목표 변경 이슈. 서비스 상대 모델 신뢰도에 직결.
## 큐
ready 미착수: #654 P2·#656 P2·#641 P3 (3). in-progress: #653 P2. 상태 라벨 없음: #463·#600. 열린 PR #599(CHANGES, d723a9c, reviewer 소유). #429 분할 남은 것: Python 사이즈-강도·텔·매트릭스 이식, field_v2 referee-change.
blocked: #391(RFC-03), #406·#427(예산, 소유자), #387(기준 3), #384(추적, #592), #385(엔진), #410(#359), #416(#389), #105. 추적: #383·#389·#341. 보류: #418·#415·#419·#306·#359·#264·#321·#320·#409 P2, #240·#327 P3. 라벨 없음: #189(D3)·#323(P3).
후보: Gate U 6인 820x1180 겹침(#541) 플레이크 1회(reviewer 09:08Z, 재발 시 이슈), #641 결과로 PRESETS_V2 c-bet 목표 변경(pro 헤즈업 SRP 53±6, TAG 58–60 검토), 4–6인 플랍 커버리지 학습(#629 mv=0도 33–45%), #624 결과로 추천 문턱 재-export·페이지 교체, 4–5인 플랍 커버리지 학습, b1Code 워커(성능 한도 초과 시), 필터 정책 LBR 재측정·mid-6 c1 교체 판단(#604 뒤, M3 대안은 화면별 인원 분포로 재판단), ADR 0021 후속 4 c1 9인 첫 측정·5 6인 단독 c1 같은 파드 D 배수, AIVAT LBR 통합·판정 반영 ADR(#634 뒤), 56k 반복 시드 2+(#555 후속 3), 평가 시드 분리(ADR 0020 한계), PHH c-bet 구분(#543 후속), E 측정 잡(#385 뒤), #391 L4·L5 재학습, 프리플랍 프로브 CI 지표(harness-change).
## 지표 요약 (최근 값과 추세)
- CI d0be4f5(11-07 22:31Z): 진행 중. CI 0988090c(11-07 21:45Z): success. CI 81025aa(11-07 19:59Z)·8989f99·77534bc·915de20: success. CI ee86d09(11-07 08:47Z): success. CI 2aaf02b(11-06 23:27Z): success, tests 1744(+4), gate_r·cash·e3 1.0, gate_l 1.0(32), stalker_loc 17132. c60f750·22a61c6 success.
- E1(CI): 착취도 초보 0.0191·중수 0.0033·고수 0.0009, Gate S 초보 분위 passed=false 지속 — 정체 축, ADR 0016 record-only.
- Gate F E1 Nash 손실: 초보 0.110·중수 0.040·고수 0.011 (정체).
- E0 CFR Kuhn 8.74e-05(안정), Leduc 0.0023338(4965e54 이후, 그 전과 비트 비교 금지).
- CI f0d2526(11-03 05:04Z): success, tests 1641, gate_r·cash·e3 1.0, gate_l 1.0(32), stalker_loc 16080. 1626→1641(3시간).
- E3 c1(CI, #521): 2.72 it/s 대 real 12.35(같은 시각) = 4.54배, CPU 맞춤 3.20(참고). 이전 #503 3.27배. regret 해시는 시드별로 같다.
- 클라우드 지출: 11월 원장 actual_usd 합 $19.79 / $100(ADR 0021, 이전 STATE 값 $9.45는 낡음).
## 경보
- [planner 11-07 20:10Z] 신규 friction: reviewer 19:24Z web E2E ECONNRESET 플레이크(PR #651, web 미변경)에도 CHANGES뿐이고 재실행 수단 없음 → infra 실패 재판정 규칙 후보(11-05 23:05Z와 같은 주제, Auditor). 판정 코멘트 오기 수정 불가(PATCH 훅 차단·GraphQL 403, (b)). 「취소된 run 빨간 집계 체크」 reviewer·reviewer-b 17:41·19:16Z 재보고((d)). quick gate 로컬 9분~1417초 builder·builder-b 3회((a)).
- [planner 11-07 15:30Z] friction 재발(4회+): builder 14:56Z `cd web/e2e` 뒤 guard 훅 상대 경로로 Bash 전체 차단 → 임시 shim으로 탈출(#647). 절대 경로(`$CLAUDE_PROJECT_DIR`) harness-change 최우선 후보 유지(Auditor). reviewer `--sweep` 일거리 없는 RUN((h)) 11-07 2회.
- [planner 11-07 13:05Z] friction 재발: builder-b 11:24Z 셸이 `web/`로 옮겨진 뒤 guard 훅 상대 경로로 Bash 전체 실패 → PR #643 CHANGES 수정 푸시 못 함(11-04·11-06 경보와 같은 주제, 3회+, 절대 경로 harness-change 최우선 후보, Auditor). builder 12:16Z quick gate 8분+((a)). reviewer 12:41Z `--sweep` 일거리 없는 RUN((h)).
- [planner 11-07 03:00Z] 신규 friction: reviewer 01:42Z가 PR #599를 짝수(reviewer-b)로 기록, reviewer-b는 홀수(reviewer)로 판단 → #599(CHANGES d723a9c, 새 커밋 없음)가 양쪽에서 빠질 위험. 홀수이므로 reviewer 소유.
- [planner 11-07 01:35Z, 01:50Z 갱신: #625는 01:42Z 머지됨, 경로 문제는 미해결] **머지 경로 없음 재발**: reviewer 01:20Z PR #625 MERGE 7a05b6f 판정 뒤 `gh pr merge` GraphQL 403·REST PUT 훅 차단, MCP 머지는 reviewer.md §2 우회 금지와 충돌한다고 보고 blocked → 판정 후 머지 정체(실험 030 성공 기준 위협). 허용 머지 경로 하나로 정하는 harness-change 최우선 후보(Auditor).
- [planner 11-06 14:50Z] friction 반복: reviewer 14:30Z `gh pr merge` GraphQL 403·REST PUT 훅 차단으로 MERGE-RETRY 실패((b), reviewer.md 지침 불일치, Auditor). planner도 라벨 제거 REST DELETE 훅 차단·`gh issue edit` GraphQL 403 → MCP.
- [planner 11-06 14:20Z] friction 반복: 취소된 이전 CI run이 같은 sha에 빨간 gates 체크를 남김(reviewer-b 14:11Z, (d)와 같은 주제). gates quick 로컬 1012초·full ~40분(builder-b 13:28Z, (a)), full ~33분(builder 13:45Z).
- [planner 11-06 12:45Z] friction 반복: 셸 cwd가 `web/app`로 바뀐 뒤 상대 경로 guard 훅이 Bash 전체 차단(builder 12:03Z, PR #609 「후속」) — 11-04 13:15Z 경보와 같은 주제(harness-change 후보, Auditor). gh GraphQL 403 → REST(reviewer-b 12:11Z, (b)). quick gate 로컬 500초 초과(builder-b 11:02Z, (a)).
- [planner 11-06 02:15Z] 신규 friction: 같은 role(builder-b) 두 세션이 같은 PR CHANGES를 동시에 고침(01:22·01:33Z, 중복 작업) → 잠금 범위 harness-change 후보(Auditor). 라벨 부착 CI 취소((d'), builder-b 01:22Z), 머지 브랜치 삭제 실패(#105, reviewer-b 02:04Z), gates 로컬 560초~40분((a)) 지속.
- [planner 11-05 23:05Z] friction 반복: web 잡 timeout으로 cancelled → 같은 sha CHANGES 뒤 재판정 불가 → builder-b가 main 머지 커밋으로 새 head(PR #594, reviewer-b 22:20Z·builder-b 22:21Z). 11-03 14:05Z 경보와 같은 주제 3회+ → infra 실패 CHANGES 재판정 규칙 harness-change 후보(Auditor).
- [planner 11-05 16:10Z] friction 반복(오늘 2회): PR을 권한 라벨(harness-change·referee-change) 붙기 전에 열어 guard가 먼저 실패 → 라벨 뒤 full CI ~40분 재실행(reviewer-b 13:30Z #590, reviewer 14:55Z #591). (d')와 같은 계열, builder가 PR 생성 시 라벨을 함께 붙이는 지침 후보(Auditor). gates quick 로컬 540~1197초((a), builder·builder-b 14:12·15:31·15:33Z). `--sweep` 일거리 없는 RUN((h), reviewer 13:42Z).
- [planner 11-06 18:20Z] friction 반복: PR #616이 main과 ARCHITECTURE.md 충돌(dirty) 상태로 열려 CI 0개 → CHANGES(reviewer-b 15:05Z, 「충돌 PR」 후보와 같은 주제, builder가 PR 전 main 최신화 확인 지침 후보). gh merge GraphQL 403·REST 훅 차단 → MCP 머지((b), reviewer-b 17:13Z). gates quick 로컬 9분+·1044초((a), builder 15:20Z·builder-b 16:31Z). `--sweep` 판정 끝난 PR만 있어도 RUN((h), reviewer 17:40Z).
- [planner 11-04 13:15Z] **friction 3회+ (area:harness 후보, Auditor 결정)**: guard 훅(`python harness/hooks/guard_bash.py`)이 상대 경로라 `cd web/e2e` 뒤 Bash 전체가 막힘 → builder-b #552 푸시 3회 실패(reviewer-b 10:11·11:15·12:20Z, PR #552 본문). 훅 명령을 절대 경로(`$CLAUDE_PROJECT_DIR`)로 바꾸는 harness-change 후보. 웹 e2e 9분+·Gate U 로컬 560초 한도 초과(builder-b·reviewer-b 12:30·13:05Z) → 백그라운드+폴링.
- **[auditor 11-01, W44]** 무결성 위반 0. 최대 비용 = MERGE 판정 후 머지 거부(#466·#480, 해소, 실험 030). main push run 60% cancelled, CHANGES 50%. 북극성 Gate A/B/C 미산출. `reports/2026-W44.md`.
- **friction 3회+ (area:harness 후보, Auditor 결정)**:
  (a) gates quick 로컬 590~971초(목표 90초), full 20~45분 — 11-01에도 builder·builder-b 반복.
  (b) gh CLI GraphQL 403 + guard 훅이 mutating gh api 차단 → MCP 우회, 지침(reviewer.md `gh pr merge`)과 불일치(reviewer·reviewer-b 11-01 4회+).
  (c) **신규**: `should_run --sweep`이 변경 없는 draft PR을 일거리로 셈 → 빈 스윕 반복, reviewer.md에 draft 규칙 없음(reviewer 11-01 4회).
  (d) 취소된 이전 CI run이 같은 sha에 failed gates 체크를 남김(reviewer-b 11-01 2회+, 10월 다수).
  (d') 11-02 builder-b·reviewer 재보고: 라벨 변경이 CI 취소 → 같은 sha 빨간 집계 체크.
  (g) docs-only PR도 gates ~41분 → 리뷰어 40분 대기 한도 초과(reviewer-b 11-02).
  (e) 장시간 CI 체인 이슈가 한 실행에 안 맞음 → 측정 이슈는 디스패치/기록 2회 실행 전제로 작성(#503 반영).
  (f) 로컬 Python 3.11 vs CI 3.12, 로컬 기본 설치에 numba 없음(.[fast]) → 프로파일 조건 불일치(builder 11-01). **11-02 reviewer-b: CI gates 잡에 numba 없어 numba 전용 테스트(#506 배치 커널)가 CI에서 skip** → CI에 `.[fast]` 설치 후보(harness-change, Auditor).
- **friction 신규(reviewer-b 11-02 12:35~14:50Z 4회)**: `needs-split` 라벨이 붙어도 planner는 머지 때나 매일만 돌아서 PR #522가 3시간 넘게 막혔다 → `needs-split` 라벨 이벤트로 planner를 트리거하는 harness-change 후보(Auditor). builder-b도 "달성 불가 기준을 착수 전에 확인할 방법이 없다"고 보고 → planner는 새 봇 메커니즘이 필요한 통계 기준을 따로 분리해 둔다.
- PR CI 지표 스냅샷 확인 불가(record-metrics가 PR run 값 미기록, 아티팩트 blob 프록시 403) → 이런 기준은 이슈에 넣지 않는다.
- 충돌 PR은 pull_request CI가 안 돈다 → CHANGES만 가능(ARCHITECTURE.md 동시 수정 충돌 반복). 후보 유지.
- 파드 로그가 밖으로 안 나와 exit 1 원인 확인 불가(builder 11-02, #491) → 실패 요약 내보내기 harness-change 후보(Auditor).
- 컨테이너 종료로 푸시 전 작업 유실 사례(builder-b #384) → 긴 작업은 WIP 푸시. guard 훅 상대 경로 문제 후보.
- RunPod 용량 부족 이력(10-31) → #401 머지, 실험 031로 재발 관찰.
- 사용자 직접 생성 이슈는 planner가 계약 형식으로 재작성(내용 보존). 실험 번호 동시 충돌·머지된 브랜치 삭제 도구 없음(#105): 후보 유지.
- NEEDS_HUMAN: NH-3·5·6·7·9·11 open. 리포 상호작용 제한 2027-04-23 만료.
- [planner 11-02 23:20Z] 신규 friction: 이슈 수용 기준이 플랍·WTSD만 단언해 턴·리버 왜곡이 테스트에 안 보였다(reviewer 21:53Z) → planner는 페르소나 이슈에 인접 스트리트 지표도 넣는다(#533 적용). reviewer-b 21:11Z: ops push 실패 시 should_run이 잠금 없이 RUN.
## 진행 중 실험 (Auditor 소유, 그대로 유지)
- **030 MERGE 판정 후 머지 재시도 (#482, PR #490 머지 11-01 03:25Z, 측정 시작).** 측정창: 머지 후 7일. 성공 기준: 판정 후 3시간 넘게 열려 있고 NH 항목도 없는 PR 0건, 같은 sha 정체 friction 3건 이하.
- 001 builder 자가 언블록 (#55, 10-25 머지). 측정창 11-08 종료. 중간값 no_work 16%(목표 ≤10%, 기준 24%).
- 009 planner run_on_merge: 잠정 성공(W44). 013 두 번째 리뷰어: 성공(W44, 머지 21→206). 문서에 결과 기록 대기.
- 015~020·023·024·028: 7일 창 종료, 판정 보류(다음 감사 우선). 나머지(002~008·010~012·014·021·022·025~027·029)는 측정 중. 실험 문서 30개 모두 '진행 중'으로 결과 기록 없음.
