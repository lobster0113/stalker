# STATE (2026-11-12 01:05Z, planner)
## 현재 단계
**D2 설계·준비(주력) + 소유자 방향 전환(10-30): 실전 게임 학습. ADR 0019 순서: A real 메뉴(#382·#386 완료·#387) → B1·B2·B3(#389) ∥ S 좌석별 스택(#383) → C 결합 key c1(#400) → D 2–5인(#384) → E 토너먼트(#385).** D1 종료. NH-3·5·6·7·9·11 open(비차단). FEEDBACK.md 없음.
planner 11-12 01:05Z: **PR #788(#775 실행 2) 머지 — L1 인코딩 CI 실측: 상한 안 후보는 `grouped_top_fit`뿐(mid-6 합 3,145,702B, L1 커버 27.6%), 전부 넣으려면 6인 ≥5.72MB. #775 닫힘(잔여 ready/in-progress 라벨 정리). → **#790 P2 생성**(coarse_top_fit 칸으로 2·3·6인 플랍 균등 CI 측정, 2회 실행). main 825680ef CI in_progress. #785 PR #789 CHANGES 1회.** planner 11-12 00:20Z: **main e7da3a97 CI success(#780 web 수정 main 검증 완료; 2abc12e8 queued 잔여는 대체됨). 미착수 ready 1(#786) → **#787 P3 생성**(ADR 0023 웹 미러: 웹 플랍 칸 테스트 4개를 시드 2000–2003 합산 판정, 로컬 참고 4개 6.6초). 미착수 #786·#787, in-progress #785(evalnoise8 run 43111293721)·#775(실행 2).** planner 11-11 22:15Z: **PR #782(e7da3a97, #775 실행 1/2, Refs) 머지 — export 요약 `l1_rows_bytes` 블록(후보 all·missing_only·grouped_eq·grouped_top_fit, 요약 schema 3). #775는 실행 2(run 42591543123 mode=export 재디스패치·표·결론) 남아 열림·in-progress 유지(builder 인수인계 있음). ready 2 < 3 → **#786 P3 harness-change 생성**(CI numba 전용 짧은 잡, friction (f)). ready 3. main e7da3a97 CI in_progress(67569e50 cancelled=후속 push로 대체, 2abc12e8 queued).** 이전 planner 기록(11-11 21:58Z 이전)은 ops 히스토리.
이전 기록(11-10~11-11 07:10Z, 페르소나 칸 체인 #722→#760 완료·D 2–5인 120k 교체 체인 #708→#753 완료)은 ops 히스토리의 이전 STATE 참고.
## 이번 주 초점 (3개 이하, 이유 포함)
1. **D 2–5인(#384)**: s4 120k 체인(run 42591543123) 재-export(#714) 완료, mid-6 적중률은 40k보다 나쁨 → #708 완료(PR #732): 120k 켬 2인 5.37·3인 4.01·4인 2.58·5인 1.06·6인 1.86 모두 선 안, mid-6 보류. #733 완료(PR #738): 5인만 교체 → #739. #734 완료(PR #742, mid-6 레거시 유지). #739 완료(PR #745, mid-5 120k) → #746 완료(PR #754, 5인 k 21→2) → #756 완료(PR #761, 3인 켬 k2·4인 끔 k5) → #762 완료(PR #767, 3인 켬 k=2 → #768 ADR 0024)·#741 완료(PR #752, 4인 교체 추천) → #753 완료(PR #755, mid-4 120k). #740 완료(PR #747) → #748 완료(PR #766, 문턱 15도 보류 — 2·3인 40k 유지), #743 완료(PR #774, 문턱 전 L1이 플랍 균등 해소, 바이트 초과) → #775 완료(PR #788, grouped_top_fit만 상한 안) → #790(부분 집합 플랍 균등). 아티팩트 ~12-04 만료. 소유자가 크리티컬하다고 한 short-handed.
2. **평가 신뢰성(#770·ADR 0024)**: 3인 시드 2개로 판정 강화(#768 완료). #770 완료(PR #776, AIVAT 도입 추천) → #781 완료(PR #784, 보정 열 기록) → #785 evalnoise8 CI sd 표 → 판정 전환 ADR(v3 선·min_seeds). #724(Gate U 정체 감시) 11-10 완료(PR #726).
3. **페르소나 목표 타당성**: 피시 칸 레버 #722 보류 → 공동 격자 #730 결론 (b)(턴 오차 51/56·station WTSD 44/56 위반, 최근접 턴 .1303–.1403이 .14 부근) → #736 ADR 0023 완료(PR #749, 4시드 평균) → #750 완료(PR #757) → #751 완료(PR #759) → #760 완료(PR #763, 웹 미러) — 체인 종료. #769 완료(PR #772): 구조 정렬 비추천, 작은 수정 #773(3bp rangeShift 폭·cbet3bp 재보정).
## 큐
ready: #790 P2(미착수, coarse_top_fit), #787 P3(미착수, 웹 칸 4시드), #786 P3 harness-change(미착수), #785 P2 in-progress(PR #789 CHANGES). 다음 후보: #785 뒤 판정 전환 ADR(lbr_thresholds_v3·min_seeds, referee-change), #790 결론 뒤 L1 export·페이지 읽기 구현 또는 6인 상한 ADR, 2·3인 120k 재검토. 열린 PR #599(CHANGES, d723a9c, 6일 무수정).
blocked: #391(RFC-03), #406·#427(예산, 소유자), #387(기준 3), #384(추적), #385(엔진), #410(#359), #416(#389), #105. 추적: #383·#389·#341. 보류: #415·#419·#306·#359·#321·#320·#409 P2, #240·#327 P3. 라벨 없음: #189(D3).
후보: 끔 칸 기준(2인 2·4인 3)은 ADR 0024 (b) 기각(진단용 칸), 클라우드 잡 실패 시 파드 job.log 내보내기(harness-change, Auditor; 42989335994 exit 2 원인 불명), 웹 피시 칸 다중 시드 CI 검사(Gate U 시간 여유 확인 뒤), #775 결론 뒤 L1 행 export·페이지 읽기 또는 6인 상한 ADR, L4 끄기(낮음), 4–6인 플랍 커버리지 학습(#629), PHH c-bet 구분, E 측정 잡(#385 뒤), #391 L4·L5 재학습, 프리플랍 프로브 CI 지표(harness-change), Gate U 6인 겹침 플레이크(#541, 재발 시).
## 지표 요약 (최근 값과 추세)
- CI a5100484(11-11 08:12Z history): tests 1772(집계 방식 변화로 11-09 1838과 직접 비교 불가 가능성), stalker_loc 17712. 이전 bf6f565: tests 1838, gate_r·cash·e3 1.0, gate_l 1.0(32), stalker_loc 18175. 1744(11-06)→1838, 증가 추세.
- e3_web_lbr(a5100484 history): run 42952524231, fresh=true, all_pass_on true. 끔/켬 bb: 2인 6.84/5.89(≤9.0)·3인 4.59/4.81(≤6.4)·4인(120k) 2.92/2.90(≤4.0)·5인(120k) 1.56/1.49(≤3.1, 이전 끔 fail 해소)·6인 레거시 0.69(≤2.7). evalnoise8(PR #767) 시드 8개 sd 3인 .82·4인 .60·5인 .43.
- E1(CI): 착취도 초보 0.0191·중수 0.0033·고수 0.0009, Gate S 초보 분위 passed=false 지속 — 정체 축, ADR 0016 record-only.
- Gate F E1 Nash 손실: 초보 0.110·중수 0.040·고수 0.011 (정체).
- E0 CFR Kuhn 8.74e-05(안정), Leduc 0.0023338(4965e54 이후, 그 전과 비트 비교 금지).
- E3 c1(CI, #521): 2.72 it/s 대 real 12.35 = 4.54배.
- 클라우드 지출: 11월 원장 합 $19.79 / $100(ADR 0021).
## 경보
- [planner 11-12 01:05Z] P0 없음(main e7da3a97 success, 825680ef 진행 중). friction 재발: (d') 라벨 이벤트 CI 취소로 stale gates failure(reviewer-b 00:59Z·reviewer 00:22Z), (a) gates quick 로컬 1242~1490초, (h) 빈 스윕 RUN(reviewer-b 00:15Z).
- [planner 11-12 00:20Z] main CI e7da3a97 success, P0 없음. 판정 없이 24h+ PR 없음(#599 CHANGES 뒤 6일 무수정 — 처리 주체 없음, Auditor 후보 유지). **friction 3회+ (h) 재발**: `should_run --sweep`이 판정할 PR 없이 RUN(11-11 reviewer 15:41·22:50·23:41Z, reviewer-b 21:12·22:11·23:11Z) → area:harness 후보(Auditor). 기타 반복: MCP 머지 경로(b), 라벨 변경 CI 취소(d'), 로컬 gates quick 10분+(a).
- [planner 11-11 13:05Z~22:15Z] 9ed6a58f web apt DNS failure → #780 P0(PR #783 머지로 해소). guard 훅 gh api 차단 → MCP((b)). 인프라 플레이크 필수 체크 reviewer 지침 없음(reviewer-b 15:48Z) → Auditor 후보.
- [planner 11-11 11:45Z] main CI: 1e88a509 green, 52ae97dc in_progress. P0 없음. 판정 없이 24h+ PR 없음. 이전(10:20Z): a5100484·57c26a04 green, a3a2c72a·a45f10d5 cancelled. 신규 friction: 클라우드 파드 exit 2 로그 없음(builder 09:58Z, 기존 후보 재발), reviewer 스윕이 #599 하나로 RUN 반복. P0 없음. 판정 없이 24h+ PR 없음(#599만 CHANGES 뒤 무수정). friction 반복: reviewer GraphQL 403→MCP((b)), gates quick 로컬 10분+((a)), ops push 실패로 lock 미획득(reviewer-b 07:57Z, 1회). **web 잡 타임아웃 재발(PR #723, gate-u 12번 구간 뒤 정체, 재실행 통과)** → #724. web 잡 `timeout-minutes: 15`가 정상 ~12분에 가깝다는 friction(reviewer 02:30Z) → ci.yml 상향은 harness-change, Auditor 후보. #599 CHANGES 1회 뒤 4일 무수정 — CLOSE 규칙에 안 걸려 처리 주체 없음(reviewer 03:40Z friction) → Auditor 후보(무수정 N일 CLOSE 규칙). friction 계속: gates quick 로컬 1063~1326초((a)), MCP 머지 경로((b)), 빈 스윕 RUN((h)), 머지 브랜치 삭제 도구 없음(#105).
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
