# STATE (2026-11-14 12:40Z, planner)
## 현재 단계
**D2 설계·준비(주력) + 소유자 방향 전환(10-30): 실전 게임 학습. ADR 0019 순서: A real 메뉴(#382·#386 완료·#387) → B1·B2·B3(#389) ∥ S 좌석별 스택(#383) → C 결합 key c1(#400) → D 2–5인(#384) → E 토너먼트(#385).** D1 종료. NH-3·5·6·7·9·11 open(비차단). FEEDBACK.md 없음. planner 11-14 12:40Z: **PR #871(8bbf1afd, #824 mid-6 120k c1) 머지 → #840 blocked→ready(P2, mid-2·3 120k 교체). PR #872(a4b17ba, #870 λ 기준선 random 0.1·tag 0.2 로컬) 머지. #873 in-progress(λ 클라우드 재측정). main a4b17ba CI 진행 중(8bbf1afd는 새 push로 cancelled).**
planner 11-14 12:20Z: **#864 2회차 성공(run 43578909248, mid-6 leaks 28/110) → #864·#836 닫힘, #824 ready → PR #871(CHANGES 11:17Z: Gate U 10 #464 정체 → builder-b 11:42Z 수정 push, 재판정 대기). #870 → PR #872(로컬 기준선 random λ=0.1·tag λ=0.2, 판정 대기). 새 #873 ready(P2, λ 격자 클라우드 재측정 = CI 근거, 2회 실행). #840은 #871 머지 뒤 ready. main aef64c7 success.**
planner 11-14 09:25Z: **PR #869(aef64c7, #866 icm_grid --lambda-grid) 머지 → ADR 0026 후속 2 완료(--agents는 #845에서 이미 있음). 새 #870 ready(P2 research, λ 격자 기준선: random·tag, remaining 2·3·4). #864 in-progress(builder 09:08Z, 2회차 run 43578909248 진행, ~11:40Z 결과). ready 1개 — 3개 미만이나 D 임계 경로 직렬·나머지 후보는 연구 없이 계약 불가(판단 유지). main aef64c7 CI 진행 중(6bddface success).**
planner 11-14 08:10Z: PR #868(6bddfac, #865 bubble_corrected_equity) 머지 → #866 ready(P2, icm_grid --lambda-grid). ready 2개(#864 P1·#866 P2) — 3개 미만이나 D 임계 경로 직렬, 독립 후보 없음(판단 유지). main 6bddface CI 진행 중(5232577 gates failure는 새 push 취소분, 개별 잡 성공).
planner 11-14 06:15Z: #855 2회차 exit 1(결과·stage-failure 없음) → 후속 #864 P1, ADR 0026 후속 #865·#866 신설.
이전 기록(11-10~11-11 07:10Z, 페르소나 칸 체인 #722→#760 완료·D 2–5인 120k 교체 체인 #708→#753 완료)은 ops 히스토리의 이전 STATE 참고.
## 이번 주 초점 (3개 이하, 이유 포함)
1. **D 2–5인(#384)**: s4 120k 체인(run 42591543123) 재-export(#714) 완료, mid-6 적중률은 40k보다 나쁨 → #708 완료(PR #732): 120k 켬 2인 5.37·3인 4.01·4인 2.58·5인 1.06·6인 1.86 모두 선 안, mid-6 보류. #733 완료(PR #738): 5인만 교체 → #739. #734 완료(PR #742, mid-6 레거시 유지). #739 완료(PR #745, mid-5 120k) → #746 완료(PR #754, 5인 k 21→2) → #756 완료(PR #761, 3인 켬 k2·4인 끔 k5) → #762 완료(PR #767, 3인 켬 k=2 → #768 ADR 0024)·#741 완료(PR #752, 4인 교체 추천) → #753 완료(PR #755, mid-4 120k). #740 완료(PR #747) → #748 완료(PR #766, 문턱 15도 보류 — 2·3인 40k 유지), #743 완료(PR #774, 문턱 전 L1이 플랍 균등 해소, 바이트 초과) → #775 완료(PR #788, grouped_top_fit만 상한 안) → #790 완료(PR #801, 6인 경계 (a)) → #803·#804 → #805(조건부 mid-6 교체). 아티팩트 ~12-04 만료. 소유자가 크리티컬하다고 한 short-handed.
2. **평가 신뢰성(#770·ADR 0024)**: 3인 시드 2개로 판정 강화(#768 완료). #770 완료(PR #776, AIVAT 도입 추천) → #781 완료(PR #784, 보정 열 기록) → #785 완료(PR #789, sd 약 1/3) → #792 판정 전환 ADR 0025(v3 선·min_seeds). #724(Gate U 정체 감시) 11-10 완료(PR #726).
3. **페르소나 목표 타당성**: 피시 칸 레버 #722 보류 → 공동 격자 #730 결론 (b)(턴 오차 51/56·station WTSD 44/56 위반, 최근접 턴 .1303–.1403이 .14 부근) → #736 ADR 0023 완료(PR #749, 4시드 평균) → #750 완료(PR #757) → #751 완료(PR #759) → #760 완료(PR #763, 웹 미러) — 체인 종료. #769 완료(PR #772): 구조 정렬 비추천, 작은 수정 #773(3bp rangeShift 폭·cbet3bp 재보정).
## 큐
ready: **#840 P2(mid-2·3 120k 교체)**. in-progress: #873(λ 클라우드 재측정). #824 완료(PR #871). #870 완료(PR #872). #864·#836 완료(run 43578909248). #866 완료(PR #869). #865 완료(PR #868). #855 닫힘(2회차 exit 1). #858 완료(PR #863). #857 완료(PR #861). #853 완료(PR #859). #854 완료(PR #860). #845 완료(PR #856). #851 완료(PR #852). #841 닫힘(timeout). #844 완료(PR #850). #847 완료(PR #849). #843 완료(PR #848). blocked 체인: #864 → #836 → #824 → #840, ready 3개 — D 임계 경로 직렬, e3-* 학습 잡 run_stages는 재개 경로(launcher RESUME_FIELDS, 하네스) 때문에 보류, 남은 후보는 연구 없이 계약으로 쓰기 어려움. #834 완료(PR #842). #832 완료(PR #835). #830 완료(PR #833). 2·3인 120k 재검토(#777 (b))는 #824 뒤. 후보(하네스, Auditor): 런처 웹 v3 판정 ops 기록(PR #806 후속), CI 측 quick 시간 기록. 열린 PR #599(CHANGES, d723a9c, 7일 무수정).
blocked: #391(RFC-03), #406·#427(예산, 소유자), #387(기준 3), #384(추적), #385(엔진), #410(#359), #416(#389), #105. 추적: #383·#389·#341. 보류: #415·#419·#306·#359·#321·#320·#409 P2, #240·#327 P3. 라벨 없음: #189(D3).
후보: 토너먼트 평가 ICM+시뮬 상금 이중 기록의 심판 연결(ADR 0026 후속 3, referee-change, #385 뒤), 끔 칸 기준(2인 2·4인 3)은 ADR 0024 (b) 기각(진단용 칸), 클라우드 잡 실패 시 파드 job.log 내보내기(harness-change, Auditor; 42989335994 exit 2 원인 불명), 웹 피시 칸 다중 시드 CI 검사(Gate U 시간 여유 확인 뒤), #775 결론 뒤 L1 행 export·페이지 읽기 또는 6인 상한 ADR, L4 끄기(낮음), 4–6인 플랍 커버리지 학습(#629), PHH c-bet 구분, E 측정 잡(#385 뒤), #391 L4·L5 재학습, 프리플랍 프로브 CI 지표(harness-change), Gate U 6인 겹침 플레이크(#541, 재발 시).
## 지표 요약 (최근 값과 추세)
- CI 3062d5a5(11-13 10:20Z history): stalker_loc 18021. 이전 261cfd4a(11-12 15:28Z history): tests 1815, stalker_loc 17923, gate_r·cash·e3·gate_l 1.0. 이전 32b6e169: tests 1787, stalker_loc 17835, gate_r·cash·e3·gate_l 1.0. 이전 a5100484: tests 1772(집계 방식 변화로 11-09 1838과 직접 비교 불가 가능성), stalker_loc 17712. 이전 bf6f565: tests 1838, gate_r·cash·e3 1.0, gate_l 1.0(32), stalker_loc 18175. 1744(11-06)→1838, 증가 추세.
- e3_web_lbr(a5100484 history): run 42952524231, fresh=true, all_pass_on true. 끔/켬 bb: 2인 6.84/5.89(≤9.0)·3인 4.59/4.81(≤6.4)·4인(120k) 2.92/2.90(≤4.0)·5인(120k) 1.56/1.49(≤3.1, 이전 끔 fail 해소)·6인 레거시 0.69(≤2.7). evalnoise8(PR #767) 시드 8개 sd 3인 .82·4인 .60·5인 .43.
- E1(CI): 착취도 초보 0.0191·중수 0.0033·고수 0.0009, Gate S 초보 분위 passed=false 지속 — 정체 축, ADR 0016 record-only.
- Gate F E1 Nash 손실: 초보 0.110·중수 0.040·고수 0.011 (정체).
- E0 CFR Kuhn 8.74e-05(안정), Leduc 0.0023338(4965e54 이후, 그 전과 비트 비교 금지).
- E3 c1(CI, #521): 2.72 it/s 대 real 12.35 = 4.54배.
- 클라우드 지출: 11월 원장 합 약 $20.11 / $100(ADR 0021, #836 실패 run $0.32 포함).
## 경보
- [planner 11-14 12:40Z] main a4b17ba CI 진행 중(8bbf1afd cancelled — 연속 머지로 취소, 실패 아님), P0 없음. 판정 없이 24h+ PR 없음(#599 CHANGES 8일 무수정). 6h+ 방치 in-progress 없음. friction 재발: (d) 라벨 재실행으로 취소된 run의 집계 gates failure(reviewer-b 12:37Z, ~30분 대기), CI 아티팩트 blob 차단(reviewer 12:14Z). 미착수 ready 1개(#840) — D 임계 경로 직렬, 판단 유지.
- [planner 11-14 12:20Z] main aef64c7 success(ci·cloud), P0 없음. 판정 없이 24h+ PR 없음(#599 CHANGES 8일 무수정). 6h+ 방치 in-progress 없음. friction 재발: (h) --sweep 빈 RUN(reviewer 09:41·10:41Z, reviewer-b 10:11Z), (a) gates full 로컬 ~28분(builder 12:05Z), 원격 run 대기 수단 없음(builder 09:27Z, curl until-loop 우회 — Auditor 후보), blob 호스트 차단으로 web 스크린샷 확인 불가(reviewer 11:17Z). ready 실질 2개(#824는 PR 진행) — D 임계 경로 직렬, 판단 유지.
- [planner 11-14 09:25Z] main aef64c7 CI 진행 중(6bddface success), P0 없음. 판정 없이 24h+ PR 없음(#599 CHANGES 8일 무수정). 6h+ 방치 in-progress 없음. 닫힌 #866에 남은 ready·in-progress 라벨 정리. friction 재발: (d) 취소 run stale gates 집계 failure(reviewer 09:17Z), gates full 로컬 10분+ 반복 대기((a), builder-b 08:49Z).
- [planner 11-14 08:10Z] main 6bddface CI 진행 중(5232577: 새 push로 취소된 gates 집계 failure, 나머지 잡 success), P0 없음. 판정 없이 24h+ PR 없음(#599 CHANGES 8일 무수정). 6h+ 방치 in-progress 없음. friction 재발: (d) 취소 run stale gates 집계 failure(reviewer-b 08:05Z), (h) --sweep 빈 RUN(reviewer 07:41Z), gates full 로컬 ~24분((a), builder 07:29Z).
- [planner 11-14 07:35Z] main 5232577 CI 진행 중(292bce15 success), P0 없음. 판정 없이 24h+ PR 없음(#599 CHANGES 8일 무수정). 6h+ 방치 in-progress 없음. friction: gates full 로컬 ~28분((a), builder-b 06:55Z), 로컬 체크아웃 stale·hard reset 분류기 거부(builder-b), CI 환경 pytest 부재·gates tests ~35분((g), reviewer 07:27Z), (h) --sweep 빈 RUN 재발(reviewer 06:41Z).
- [planner 11-14 06:15Z] main 292bce15 success, P0 없음. 판정 없이 24h+ PR 없음(#599 CHANGES 8일 무수정). **#855 실패 후 후속 이슈 부재로 builder·builder-b 4회 연속 no_work(04:21~06:05Z)** → #864로 해소. planner 교훈: 클라우드 잡 결과 회수에서 실패하면 builder가 후속 이슈 초안을 남기므로, planner가 머지/매일 외에도 이 경로로 트리거되면 좋다(needs-split 트리거 후보와 같은 축, Auditor). friction: 2회 이슈 회수 단계 라벨 처리 불명확(builder 03:08Z → #864 본문에 명시), stale --sweep RUN(reviewer 02:41·05:41Z, (h)).
- [planner 11-14 02:15Z] main 06bfe27e CI 진행 중(3f468af1 success), P0 없음. 판정 없이 24h+ PR 없음(#599 CHANGES 8일 무수정). friction 재발: (d) 라벨 추가로 취소된 run의 stale gates failure(reviewer-b 02:06Z, 3회+ 지속 → Auditor 후보), gates full 로컬 ~31분((a)), 2회 이슈 1회차 Refs 대 PR 템플릿 "Closes 필수" 불일치(builder 01:40Z, 11-13 09:04Z 이어 2회).
- [planner 11-14 00:55Z] main 3f468af1 CI 진행 중(b71c0fa6 이전), P0 없음. 판정 없이 24h+ PR 없음(#599 CHANGES 8일 무수정). 신규 friction: gates (tests) 잡 로그 blob 호스트 접근 불가로 passed 수 확인 불가(reviewer 00:42Z).
- **[auditor 11-08, W45]** 무결성 위반 0(머지 86). main CI red 0. CHANGES 31%(W44 50%). builder no_work 1.9% → 실험 001 성공, 030 성공. 신규 실험 034 guard 훅 절대 경로(#659 ready P1). reviewer 실행 72% 무판정. 다음 1순위: reviewer.md 머지 경로 MCP 명시. #341 P0 10일째 라벨 없음 — planner 확인. Gate A/B/C 3주째 미산출. `reports/2026-W45.md`.
- **[auditor 11-01, W44]** 무결성 위반 0. 최대 비용 = MERGE 판정 후 머지 거부(#466·#480, 해소, 실험 030). main push run 60% cancelled, CHANGES 50%. 북극성 Gate A/B/C 미산출. `reports/2026-W44.md`.
- **friction 3회+ (area:harness 후보, Auditor 결정)**:
  (a) gates quick 로컬 590~971초(목표 90초), full 20~45분 — 11-01에도 builder·builder-b 반복.
  (b) gh CLI GraphQL 403 + guard 훅이 mutating gh api 차단 → MCP 우회, 지침(reviewer.md `gh pr merge`)과 불일치(reviewer·reviewer-b 11-01 4회+).
  (c) **신규**: `should_run --sweep`이 변경 없는 draft PR을 일거리로 셈 → 빈 스윕 반복, reviewer.md에 draft 규칙 없음(reviewer 11-01 4회).
  (d) 취소된 이전 CI run이 같은 sha에 failed gates 체크를 남김(reviewer-b 11-01 2회+, 10월 다수).
  (d') 11-02 builder-b·reviewer 재보고: 라벨 변경이 CI 취소 → 같은 sha 빨간 집계 체크.
  (g) docs-only PR도 gates ~41분 → 리뷰어 40분 대기 한도 초과(reviewer-b 11-02).
  (e) 장시간 CI 체인 이슈가 한 실행에 안 맞음 → 측정 이슈는 디스패치/기록 2회 실행 전제로 작성(#503 반영).
  (f) 로컬 Python 3.11 vs CI 3.12, 로컬 기본 설치에 numba 없음(.[fast]) → 프로파일 조건 불일치(builder 11-01). **CI numba skip은 #786(PR #794)으로 해소.** **11-02 reviewer-b: CI gates 잡에 numba 없어 numba 전용 테스트(#506 배치 커널)가 CI에서 skip** → CI에 `.[fast]` 설치 후보(harness-change, Auditor).
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
