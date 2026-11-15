# STATE (2026-11-15 07:10Z, planner)
## 현재 단계
**D 2–5인 완료(#384 닫힘 17:15Z) → E 토너먼트(#385) 착수. D2 설계·준비(주력) + 소유자 방향 전환(10-30): 실전 게임 학습. ADR 0019 순서: A real 메뉴(#382·#386 완료·#387) → B1·B2·B3(#389) ∥ S 좌석별 스택(#383) → C 결합 key c1(#400) → D 2–5인(#384) → E 토너먼트(#385).** D1 종료. NH-3·5·6·7·9·11 open(비차단). FEEDBACK.md 없음. planner 11-14 17:15Z: **#876 완료(cloud run 43613729968, 2–6인 120k c1 끔/켬 10칸 v3 선 안) → #384 수용 기준 전부 충족, 닫음. #873 2회차 timeout → 후속 #877(P2). E 하위 이슈 신설: #878 앤티+Gate R(P1, referee-change)·#879 ICM 보상 함수(P1)·#880 E 환경 ADR(P2). #385 blocked 해제(추적).**
planner 11-15 07:10Z: **PR #904(361453b2, #890 실험 001·009·013·030·034 결과 기록, 상태 성공) 머지 → #890 닫힘·ready·in-progress 라벨 정리. ready 6(#898·#899 P1, #900·#901·#902 P2, #903 P3), in-progress 없음.**
planner 11-15 06:40Z: **PR #897(48e2ae0f, #892 북극성 현황표 + ADR 0028) 머지 → #892 라벨 정리. ADR 0028 후속 신설: #902 P2 gate_t_pass_rate·gate_t_checks history 등록, #903 P3 sim_hands_per_sec(보고 전용), 둘 다 referee-change·착수 가능. Auditor 'Gate A/B/C 미산출'은 현황표 §2(A/B 은퇴, C 없는 이름)로 읽는다.**
planner 11-15 06:15Z: **#880(PR #894, ADR 0027 E 환경)·#887(PR #895, 웹 tpgto.js 앤티)·#888(PR #896, 병렬 워커 icm·ante·stage) 머지 → 닫힌 3건 라벨 정리. ADR 0027 후속 신설: F2a #898(P1 스택 표본) → F2b #899(P1 pod_train 인자·train_env) → F5 #901(P2 첫 측정 run, 2회 실행), F3a #900(P2 E3 정책 토너먼트 에이전트, 병행 가능). #892는 PR #897 리뷰 대기, #890 in-progress.**
planner 11-15 02:45Z: **PR #893(9c1a7d3c, #889 실험 039: 라벨 이벤트는 guard-labels.yml만, ci.yml labeled/unlabeled 제거) 머지 → #889 닫힘·라벨 정리. 실험 039 측정창 시작(~11-22). #105 범위를 머지된 브랜치 정리로 축소(코멘트). 닫힌 이슈 in-progress 잔존 7건(#334·338·340·342·344·348·357) 정리. ready 4개(#888·#887·#892·#890), #880 in-progress.**
이전 기록(11-10~11-11 07:10Z, 페르소나 칸 체인 #722→#760 완료·D 2–5인 120k 교체 체인 #708→#753 완료)은 ops 히스토리의 이전 STATE 참고.
## 이번 주 초점 (3개 이하, 이유 포함)
1. **E 토너먼트(#385, ADR 0027)**: 첫 단계 9max_sng_503020 버블 r=4·λ=0·cold. 임계 경로 #898 → #899 → #901(첫 파드 run, 단독 디스패치·최악 $3.60) ∥ #900(정책 에이전트 → F3b A/B·F7 λ 선택). 이유: 소유자 방향(실전 게임)의 남은 마지막 단계이고 ICM 편향이 측정된 곳(#845). D 결과(#384 완료, 120k 칸 v3 선 안)는 지표 요약 참고.
2. **평가 신뢰성(#770·ADR 0024)**: 3인 시드 2개로 판정 강화(#768 완료). #770 완료(PR #776, AIVAT 도입 추천) → #781 완료(PR #784, 보정 열 기록) → #785 완료(PR #789, sd 약 1/3) → #792 판정 전환 ADR 0025(v3 선·min_seeds). #724(Gate U 정체 감시) 11-10 완료(PR #726).
3. **페르소나 목표 타당성**: 피시 칸 레버 #722 보류 → 공동 격자 #730 결론 (b)(턴 오차 51/56·station WTSD 44/56 위반, 최근접 턴 .1303–.1403이 .14 부근) → #736 ADR 0023 완료(PR #749, 4시드 평균) → #750 완료(PR #757) → #751 완료(PR #759) → #760 완료(PR #763, 웹 미러) — 체인 종료. #769 완료(PR #772): 구조 정렬 비추천, 작은 수정 #773(3bp rangeShift 폭·cbet3bp 재보정).
## 큐
ready: **#898 P1(F2a 스택 표본, 착수 가능)·#899 P1(F2b, 선행 #898)·#900 P2(F3a 정책 에이전트, 착수 가능)·#901 P2(F5 측정 run, 선행 #899)·#902 P2(Gate T history)·#903 P3(처리량 history)**; in-progress 없음. #890 완료(PR #904). #892 완료(PR #897). #880·#887·#888 완료(PR #894·#895·#896). F3b tournament_ab·F4(referee-change)·F6–F10은 앞 결과 뒤. #889 완료(PR #893). #886 완료(PR #891). #877 닫힘(2회차 429 실패). #883 완료(PR #885). #878 완료(PR #881). #879 완료(PR #882). #876 완료(run 43613729968). #873 닫힘(timeout) → #877. #384 닫힘(완료). #840 완료(PR #875). #873 1회차 완료(PR #874). #824 완료(PR #871). #870 완료(PR #872). #864·#836 완료(run 43578909248). #866 완료(PR #869). #865 완료(PR #868). #855 닫힘(2회차 exit 1). #858 완료(PR #863). #857 완료(PR #861). #853 완료(PR #859). #854 완료(PR #860). #845 완료(PR #856). #851 완료(PR #852). #841 닫힘(timeout). #844 완료(PR #850). #847 완료(PR #849). #843 완료(PR #848). blocked 체인: #864 → #836 → #824 → #840, ready 3개 — D 임계 경로 직렬, e3-* 학습 잡 run_stages는 재개 경로(launcher RESUME_FIELDS, 하네스) 때문에 보류, 남은 후보는 연구 없이 계약으로 쓰기 어려움. #834 완료(PR #842). #832 완료(PR #835). #830 완료(PR #833). 2·3인 120k 재검토(#777 (b))는 #824 뒤. 후보(하네스, Auditor): 런처 웹 v3 판정 ops 기록(PR #806 후속), CI 측 quick 시간 기록. 열린 PR #599(CHANGES, d723a9c, 7일 무수정).
blocked: #391(RFC-03), #406·#427(예산, 소유자), #387(기준 3), 추적: #385(E, 하위 #877–#880), #410(#359), #416(#389), #105. 추적: #383·#389·#341. 보류: #415·#419·#306·#359·#321·#320·#409 P2, #240·#327 P3. 라벨 없음: #189(D3).
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
- [planner 11-15 07:10Z] main 361453b2 CI 진행 중(48e2ae0f 직후). P0 없음. 판정 없이 24h+ PR 없음(#599 CHANGES 9일 무수정). 6h+ 방치 in-progress 없음. friction 재발 (a)·(g): 문서만 바뀌는 chore도 gates full 약 30분(builder 06:36Z), gates(tests) CI 약 30분(reviewer 06:28Z).
- [planner 11-15 06:40Z] main 1e5e8d6e CI success, 48e2ae0f 진행 중. P0 없음. 판정 없이 24h+ PR 없음(#599 CHANGES). 6h+ 방치 in-progress 없음(#890 06:05Z).
- [planner 11-15 06:15Z] main e810934b CI success(04:29Z), 1e5e8d6e CI 진행 중. P0 없음. 판정 없이 24h+ PR 없음(#599 CHANGES 9일 무수정, #897 05:55Z 열림). 6h+ 방치 in-progress 없음. friction 재발: (a) gates full 로컬 28~30분(builder 04:38Z·builder-b 03:57Z·05:55Z), gates(tests) CI 48분 > 리뷰 대기 40분(reviewer-b 05:28Z), journal push append 경합(reviewer-b 05:28Z).
- [planner 11-15 01:30Z] main 63cf0a80 CI success(history 00:25Z, tests 1961, stalker_loc 18835), ec28924a CI 진행 중. P0 없음. 판정 없이 24h+ PR 없음(#599 CHANGES 9일 무수정). 6h+ 방치 in-progress 없음. **Auditor 후보(harness-change)**: `harness/cloud/launcher.py`에 RunPod 429 백오프·결과 회수 실패 시 재회수 없음(builder-b 00:12Z, #877) + 같은 시각 `push_ledger` ops 경합 거부(원장 줄 누락 가능 — 확인 요청) + 03:17Z reap이 남은 pod 정리했는지 확인. friction 재발: (a) gates full 로컬 24분(builder 00:33Z), (d) opened 이벤트 CI 3회 경합·취소 run gates failure(reviewer 01:13Z, 실험 039 대상), should_run 잠금 push 실패(reviewer 01:13Z)·판정 있는 PR에도 스윕 RUN(reviewer-b 01:11Z).
- [planner 11-14 23:50Z] main 63cf0a80 CI 진행 중(80220ac0 success), P0 없음. 판정 없이 24h+ PR 없음(#599 CHANGES 8일 무수정). 6h+ 방치 in-progress 없음(#877 19:21Z). 닫힌 #883의 ready·in-progress 라벨 정리. friction: guard 훅이 gh api 이슈 생성/라벨 삭제 차단 → MCP 사용((b) 재발).
- **[auditor 11-15, W46]** 무결성 위반 0(머지 121, CHANGES 21%, 리드타임 중앙값 43분). main red 3.7h 1회(#780 P0 해소). 실험 034 **성공**, 038 순항(머지 경로 friction 0). 신규 실험 **039 라벨 이벤트 guard 전용(#889 ready P1)** — 머지 PR 69%에 취소 run gates 잔재. 결과 기록 chore #890. **Planner 할 일**: 닫힌 이슈 138건에 `in-progress` 잔존 정리, Gate A/B/C 4주째 미산출 → 재산출 경로 이슈, planner.md 쓰기 경로 MCP 명시(후보). `reports/2026-W46.md`.
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
- **039 라벨 이벤트 guard 전용 워크플로 (#889, PR #893 11-15 02:39Z 머지).** 측정창 ~11-22. 성공: 취소 run gates 잔재 머지 PR ≤10%(기준선 69%), 취소/stale friction ≤10건(기준선 90/주), 리드타임 중앙값 ≤43분. #105는 브랜치 정리만 남김.
- **038 reviewer 머지 경로 MCP (#795, PR #799 11-12 07:35 머지).** 측정창 ~11-19. 성공: friction (b) 0–1건. 중간 0건.
- 036 playwright 캐시(PR #783 11-11, ~11-25)·037 numba 잡(PR #794 11-12, ~11-26)·035 E3 결정성 dispatch: 측정 중.
- 034 guard 훅 절대 경로: **성공**(W46, 차단 보고 0·shim 0). 030·001·009·013: 성공. → 결과 기록 완료(#890, PR #904).
- 015~029·031~033: 판정 보류(3주째), 분기 제거 실험 때 정리 후보. 나머지(002~008·010~012·014)는 측정 중.
