# STATE (2026-11-08 19:30Z, planner)
## 현재 단계
**D2 설계·준비(주력) + 소유자 방향 전환(10-30): 실전 게임 학습. ADR 0019 순서: A real 메뉴(#382·#386 완료·#387) → B1·B2·B3(#389) ∥ S 좌석별 스택(#383) → C 결합 key c1(#400) → D 2–5인(#384) → E 토너먼트(#385).** D1 종료. NH-3·5·6·7·9·11 open(비차단). FEEDBACK.md 없음(11-01 19:10Z 확인).
planner 11-08 12:55Z: **PR #675(7f3c775, #670 페르소나 플랍 칸 레버) 12:49Z 머지** → #670 ready·in-progress 정리(MCP). 결론(로컬 참고): pro 칸 헤즈업·싱글 55.0·헤즈업·3bp 62.6·멀티웨이·싱글 27.5·폴드 헤즈업·싱글 41.9 모두 ±6 안, pro probe_turn·giveup_turn 재적합(lag WTSD 가드). 후속 → 신규 **#676 P2**(웹 pro 페르소나 칸 목표, area:service — 서비스가 실제 쓰는 상대), **#677 P3**(tag 칸 수준 연구). main CI 7f3c775 진행 중, 5170ac3 success. ready 미착수 3(#676·#600·#677), in-progress #674.
planner 11-08 14:45Z: **PR #679(7d84df2, #676 웹 pro 페르소나 플랍 칸) 14:37Z 머지** → #676 닫힘·라벨 정리(MCP). 결론(로컬 참고): 웹 pro hu_srp c-bet 52.8·hu_3bp 64.1·mw_srp 31.0·폴드 hu_srp 44.4 모두 ±6 안, 합계 cbet 54.0·FCB 37.1 범위 안. 신규 **#680 P3**(mixn c1 시드 4 이어 학습 잡 40k→120k 정의, #656 재판단 조건·~12-03 만료 전). #674 PR #678 CHANGES 해결 푸시(14:21Z) 재판정 대기. main CI 7d84df2 진행 중, 7f3c775 success. ready 미착수 3(#677·#600·#680), in-progress #674.
planner 11-08 18:05Z: **PR #682(758cc0f, #600 복습 스케줄러 스파이크) 머지(693158f)**, #681(#677 tag 칸 연구)·#678(#674 s3 기록) 머지 → #600·#677·#674 라벨 정리(MCP). 결론(**CI**): 복습 run 42504068705 — 14일 시험 차이 0, 60일 이득은 고정이 11일에 멈춘 탓(fixed_long≈Leitner, 복습 5.4 대 8.0) → 적응형 채택 안 함, 웹에 복습 스케줄러 없음 → 후속 없음. LBR s3 run 42480052070 — 서비스(켬) 2–6인 모두 선 아래, 현 페이지 유지 확정(5인 끔 3.119>3.1, 판정 대상 아님). 신규 **#683 P2 referee-change**(지표 스냅샷에 e3_web_lbr — W45 북극성 history 공백 대응), **#684 P2**(tag 칸 레버, #677 초안). main CI 656985c success(tests 1814). ready 미착수 3(#683·#684·#680).
planner 11-08 19:30Z: **PR #685(3e89f39, #683 지표 스냅샷 e3_web_lbr) 머지(caf85e7)** → #683 라벨 정리(MCP). 다음 main metrics 스냅샷에서 history에 `e3_web_lbr`가 null이 아닌지 확인 필요(ci.yml에서 snapshot이 ops worktree 전에 돎 — fetch로 읽게 구현됨). null이면 P1 후속. 신규 **#687 P3**(pro PFR 목표 21→18.5, population-stats 권고 1). PR #686(#684 tag 칸 레버) 판정 대기. ready 미착수 2(#680·#687), in-progress #684.
## 이번 주 초점 (3개 이하, 이유 포함)
1. **D 2–5인(#384)**: 평가기(#534)·인원별 값(#542)·시드 분산(#548·#559) → 합격선 ADR 0020 머지(#564) → #572 판정기 머지(c1 2–6인 pass) → #576 기록 연결 머지 → #581 ADR 0021 머지(mixn c1 한 정책) → #583 웹 c1 key 미러 머지 → #585 인원별 내보내기 머지 → #588 CI 내보내기 머지 → #592 시드 M4·문턱 선택 머지 → #596 인원별 문턱·ops 정책 경로 머지 → #601 재-export 실측 머지(전 인원 상한 안) → #604 2–5인 반입·c1 키 라우팅 머지(프리플랍만) → #606 b1 칸 JS 이식 머지 → #608 포스트플랍 c1 키 머지 → #610·#611·#615 머지 → #618 ADR 0022 머지(런타임 거친 키 백오프) → #624 실측 머지(#629: 다인 플랍은 커버리지 탓) → #623 페이지 백오프 머지(#633) → #635 머지(#636: mid-6 교체 보류) → #631 머지(#639: 2인 mv=5 상한 안) → #638 머지(#642: 꼬리 키, 자리 묶음 L3 추천) → #644 머지(#646: np.empty 버그) → #645 머지(#647: L3 3·6인 −8–14%p) → #640 머지(#643: 2인 mv=5 반입) → #648 머지(#649: L4 3·4·6인 −6–11%p) → #652 머지(#655: L4 페이지 미러) → #654 머지(#658: 평균 근사 ≈ 균등) → #653 머지(#657: 판단 불가, 3인 켬 선 초과) → #656 머지(#663: mid-6 교체 보류) → #660 머지(#664: mean 유지, L4 제거 후보) → #661 머지(#665) → #666 머지(#668: L4 영향 0.2%, 끄기 급하지 않음) → #669 머지(#671: 10칸 통과, 현 페이지 유지) → #672 머지(#673: s3 잡) → #674 머지(#678: s3 5칸 통과, 페이지 확정) → 남은 레버 커버리지(#680). 소유자가 크리티컬하다고 한 short-handed.
2. **북극성 CI 공백(#683 머지)**: 서비스 정책 LBR을 스냅샷에 옮김(PR #685) → 다음 main history 줄에 e3_web_lbr 실림 확인, 이후 기울기 추적(심판 우선 규칙). C 고수 체인(#479)은 b2 추가 안 함으로 정리됨.
3. **페르소나 목표 타당성**: #670 머지(PR #675, Python pro 칸 목표 통과) → #676 웹 pro 미러 머지(PR #679) → #677 머지(#681) → **#684 tag 칸 레버**(웹 미러는 그 뒤). 서비스 상대 모델 신뢰도에 직결.
## 큐
ready 미착수: #680 P3·#687 P3 (2). in-progress #684(PR #686). ready 라벨 계 3. #341 P1 추적. 상태 라벨 없음: #463. 열린 PR #599(CHANGES, d723a9c, reviewer 소유, 2일+ 무수정). #429 분할 남은 것: Python 사이즈-강도·텔·매트릭스 이식, field_v2 referee-change.
blocked: #391(RFC-03), #406·#427(예산, 소유자), #387(기준 3), #384(추적, #592), #385(엔진), #410(#359), #416(#389), #105. 추적: #383·#389·#341. 보류: #418·#415·#419·#306·#359·#264·#321·#320·#409 P2, #240·#327 P3. 라벨 없음: #189(D3)·#323(P3).
후보: 웹 tag 칸 미러(#684·PR #686 머지 뒤 바로 이슈화), L4 끄기(tpgto.js backoffRow·neighbor_row·ADR 0022, 코드 단순화만 이점 — 낮음), mid-6 c1 교체 재판단(#669 CI 걸러 낸 mid-6 켬 1.628 통과, #656 보류 조건은 플랍 균등·더 긴 학습), Gate U 6인 820x1180 겹침(#541) 플레이크 1회(재발 시 이슈), 4–6인 플랍 커버리지 학습(#629 mv=0도 33–45%), #624 결과로 추천 문턱 재-export·페이지 교체, 4–5인 플랍 커버리지 학습, b1Code 워커(성능 한도 초과 시), 필터 정책 LBR 재측정·mid-6 c1 교체 판단(#604 뒤, M3 대안은 화면별 인원 분포로 재판단), ADR 0021 후속 4 c1 9인 첫 측정·5 6인 단독 c1 같은 파드 D 배수, AIVAT LBR 통합·판정 반영 ADR(#634 뒤), 56k 반복 시드 2+(#555 후속 3), 평가 시드 분리(ADR 0020 한계), PHH c-bet 구분(#543 후속), E 측정 잡(#385 뒤), #391 L4·L5 재학습, 프리플랍 프로브 CI 지표(harness-change).
## 지표 요약 (최근 값과 추세)
- CI 558c8b9(11-08 06:30Z)·93e4511·56cd831·ee7a35f·46fa038: success. fad7239: cancelled(후속 push). CI 1a66aa0(11-08 00:27Z)·d0be4f5(11-07 22:31Z): success. CI 0988090c(11-07 21:45Z): success. CI 81025aa(11-07 19:59Z)·8989f99·77534bc·915de20: success. CI ee86d09(11-07 08:47Z): success. CI 2aaf02b(11-06 23:27Z): success, tests 1744(+4), gate_r·cash·e3 1.0, gate_l 1.0(32), stalker_loc 17132. c60f750·22a61c6 success.
- E1(CI): 착취도 초보 0.0191·중수 0.0033·고수 0.0009, Gate S 초보 분위 passed=false 지속 — 정체 축, ADR 0016 record-only.
- Gate F E1 Nash 손실: 초보 0.110·중수 0.040·고수 0.011 (정체).
- E0 CFR Kuhn 8.74e-05(안정), Leduc 0.0023338(4965e54 이후, 그 전과 비트 비교 금지).
- CI f0d2526(11-03 05:04Z): success, tests 1641, gate_r·cash·e3 1.0, gate_l 1.0(32), stalker_loc 16080. 1626→1641(3시간).
- E3 c1(CI, #521): 2.72 it/s 대 real 12.35(같은 시각) = 4.54배, CPU 맞춤 3.20(참고). 이전 #503 3.27배. regret 해시는 시드별로 같다.
- 클라우드 지출: 11월 원장 actual_usd 합 $19.79 / $100(ADR 0021, 이전 STATE 값 $9.45는 낡음).
## 경보
- [planner 11-08 19:30Z] main CI red 0(693158f success, caf85e7 진행 중). 판정 없이 24h+ PR: #599 유지(#600이 같은 주제로 결론 냄 — 미채택 — #599는 reviewer가 CLOSE 검토 후보). friction(로컬 참고): builder 18:42Z quick timeout 잘림, builder-b 19:13Z quick 1240초((a) 재발).
- [planner 11-08 18:05Z] main CI red 0(656985c success). 판정 없이 24h+ PR: #599 유지(#600 노트가 #599 미머지 노트를 참조 못 함 — builder-b friction). friction(로컬 참고): reviewer-b 17:00Z CI(tests) 끝나기 전 CHANGES 판정, reviewer 17:40Z 홀수 PR 없는데 --sweep RUN((h) 재발), gates quick 18분(경합, (a)).
- [planner 11-08 14:45Z] main CI red 0(7d84df2 진행 중). 판정 없이 24h+ PR: #599 유지. friction(로컬 참고): reviewer 14:38Z MCP 머지 경로 reviewer.md 미기재((b) 재발), builder 14:06Z 1코어 quick 1177초((a)).
- [planner 11-08 12:55Z] main CI red 0(7f3c775 진행 중). 판정 없이 24h+ PR: #599 유지. friction(로컬 참고): builder 12:04Z 이슈 기준 「기존 합계 지표 유지」가 칸 목표와 설계상 충돌 → planner가 칸 목표 이슈에 합계 기준을 같이 넣지 않도록 반영(#676에 대체 허용 명시). (a) quick 1371초 재발.
- [planner 11-08 12:10Z] main CI red 0(5170ac3 진행 중). 판정 없이 24h+ PR: #599 유지. friction(로컬 참고): reviewer 11:58Z 「측정 이슈에 Closes #N → 머지 뒤 기준 남은 채 닫힘」(#661→#669, #672→#674 2회째) — 측정 이슈는 잡 PR에 `Refs`를 쓰거나 처음부터 잡/기록 2이슈로 나누는 지침 후보(Auditor). gh merge 403·REST 훅 차단 → MCP 머지((b)), 머지 브랜치 삭제 도구 없음(#105). builder-b gates quick 1274초((a)).
- [planner 11-08 10:30Z] main CI red 0(4720829 진행 중). 판정 없이 24h+ PR: #599 유지. 신규 friction 없음(이번 실행).
- [planner 11-08 09:35Z] main CI red 0(d70d438 진행 중). 판정 없이 24h+ PR: #599 유지. friction(로컬 참고): reviewer-b 07:45Z 웹훅·07:49Z 스윕 같은 PR 이중 판정(잠금 ops push 실패) 재확인, 머지 뒤 작업 브랜치 삭제 경로 없음(#105 같은 주제), gates full 로컬 tests 1651초((a)).
- [planner 11-08 08:20Z] main CI red 0. 판정 없이 24h+ PR: #599 유지(CHANGES 뒤 2일+ 새 커밋 없음). friction(로컬 참고): reviewer-b 07:45/07:49Z 웹훅 실행과 스윕이 같은 PR(#668) 동시 판정 — ops push 실패로 잠금 미획득(신규, Auditor). quick gate 로컬 1301–1444초((a) 재발 builder·builder-b). ARCHITECTURE.md tools 한 줄 충돌 재발(#665, 3회+ 후보 유지).
- [planner 11-08 04:40Z] main CI red 0(확인된 것 기준). 판정 없이 24h+ PR: #599 유지. friction(로컬 참고): reviewer-b 03:10Z `--sweep` 짝수 PR 없어도 RUN((h) 재발), 취소 run 빨간 집계 체크((d), reviewer-b 02:28Z), gates quick 로컬 1268초((a)). Auditor 다음 1순위(reviewer.md MCP 머지 경로) 대기.
- **[auditor 11-08, W45]** 무결성 위반 0(머지 86). main CI red 0. CHANGES 31%(W44 50%). builder no_work 1.9% → 실험 001 성공, 030 성공. 신규 실험 034 guard 훅 절대 경로(#659 ready P1). reviewer 실행 72% 무판정. 다음 1순위: reviewer.md 머지 경로 MCP 명시. #341 P0 10일째 라벨 없음 — planner 확인. Gate A/B/C 3주째 미산출. `reports/2026-W45.md`.
- [planner 11-07 20:10Z] 신규 friction: reviewer 19:24Z web E2E ECONNRESET 플레이크(PR #651, web 미변경)에도 CHANGES뿐이고 재실행 수단 없음 → infra 실패 재판정 규칙 후보(11-05 23:05Z와 같은 주제, Auditor). 판정 코멘트 오기 수정 불가(PATCH 훅 차단·GraphQL 403, (b)). 「취소된 run 빨간 집계 체크」 reviewer·reviewer-b 17:41·19:16Z 재보고((d)). quick gate 로컬 9분~1417초 builder·builder-b 3회((a)).
- [planner 11-07 15:30Z] friction 재발(4회+): builder 14:56Z `cd web/e2e` 뒤 guard 훅 상대 경로로 Bash 전체 차단 → 임시 shim으로 탈출(#647). 절대 경로(`$CLAUDE_PROJECT_DIR`) harness-change 최우선 후보 유지(Auditor). reviewer `--sweep` 일거리 없는 RUN((h)) 11-07 2회.
- [planner 11-07 13:05Z] friction 재발: builder-b 11:24Z 셸이 `web/`로 옮겨진 뒤 guard 훅 상대 경로로 Bash 전체 실패 → PR #643 CHANGES 수정 푸시 못 함(11-04·11-06 경보와 같은 주제, 3회+, 절대 경로 harness-change 최우선 후보, Auditor). builder 12:16Z quick gate 8분+((a)). reviewer 12:41Z `--sweep` 일거리 없는 RUN((h)).
- [planner 11-07 01:35Z, 01:50Z 갱신: #625는 01:42Z 머지됨, 경로 문제는 미해결] **머지 경로 없음 재발**: reviewer 01:20Z PR #625 MERGE 7a05b6f 판정 뒤 `gh pr merge` GraphQL 403·REST PUT 훅 차단, MCP 머지는 reviewer.md §2 우회 금지와 충돌한다고 보고 blocked → 판정 후 머지 정체(실험 030 성공 기준 위협). 허용 머지 경로 하나로 정하는 harness-change 최우선 후보(Auditor).
- [planner 11-06 18:20Z] friction 반복: PR #616이 main과 ARCHITECTURE.md 충돌(dirty) 상태로 열려 CI 0개 → CHANGES(reviewer-b 15:05Z, 「충돌 PR」 후보와 같은 주제, builder가 PR 전 main 최신화 확인 지침 후보). gh merge GraphQL 403·REST 훅 차단 → MCP 머지((b), reviewer-b 17:13Z). gates quick 로컬 9분+·1044초((a), builder 15:20Z·builder-b 16:31Z). `--sweep` 판정 끝난 PR만 있어도 RUN((h), reviewer 17:40Z).
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
## 진행 중 실험 (Auditor 소유, 그대로 유지)
- **034 guard 훅 절대 경로 (#659, PR #662 11-08 02:28Z 머지).** 측정창 11-08~11-15. 성공: 훅 경로 Bash 차단 보고 0–1건(기준선 22/주), shim 0, 푸시 실패 PR 0.
- 030 머지 재시도: **성공**(W45, 3시간+ 정체 0, 재시도 6/6 머지). 001 builder 자가 언블록: **성공**(no_work 1.9%). 009·013: 성공. → 결과 기록 chore 이슈는 다음 감사(harness-change).
- 015~020·023·024·028: 판정 보류(2주째). 나머지(002~008·010~012·014·021·022·025~027·029·031~033)는 측정 중. 실험 문서 35개 모두 '진행 중'으로 결과 기록 없음.
