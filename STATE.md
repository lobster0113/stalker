# STATE (2026-11-17 01:10Z, planner)
## 현재 단계
**D 2–5인 완료(#384 닫힘 17:15Z) → E 토너먼트(#385) 착수. D2 설계·준비(주력) + 소유자 방향 전환(10-30): 실전 게임 학습. ADR 0019 순서: A real 메뉴(#382·#386 완료·#387) → B1·B2·B3(#389) ∥ S 좌석별 스택(#383) → C 결합 key c1(#400) → D 2–5인(#384) → E 토너먼트(#385).** D1 종료. NH-3·5·6·7·9·11 open(비차단). FEEDBACK.md 없음. planner 11-14 17:15Z: **#876 완료(cloud run 43613729968, 2–6인 120k c1 끔/켬 10칸 v3 선 안) → #384 수용 기준 전부 충족, 닫음. #873 2회차 timeout → 후속 #877(P2). E 하위 이슈 신설: #878 앤티+Gate R(P1, referee-change)·#879 ICM 보상 함수(P1)·#880 E 환경 ADR(P2). #385 blocked 해제(추적).**
planner 11-17 01:10Z: **PR #954(c24630f9, #952 RunPod REST v2 `api.runpod.io/v2` 이전 + check REST 도달 검사) 머지 → #952 닫힘·라벨 정리 → #937 blocked 해제·ready(check 후 쌍 2 재디스패치). ready 3(착수 가능 #937·#955; #935는 #937 뒤).**
planner 11-17 01:00Z: **PR #953(ecf99204, #945 F8a ADR 0029 토너먼트 정책 웹 내보내기·표시) 머지 → #945 닫힘·라벨 정리. ADR 0029 후속: 신설 #955 H1 `cloud.yml mode=export` export_kind+인덱스 v2(P2, ready, harness-change, 클라우드 없음)·#956 H2 웹 로드·단계 매핑(P2, blocked: #955). H3(표시·복기)·H4(첫 실제 export, #937 판정 뒤)는 H2·#937 뒤 신설. #952는 PR #954 진행. ready 3(착수 가능 #955; #952 PR 중, #935는 #937 뒤).**
planner 11-16 23:15Z: **PR #951(59646c6e, #949 CI tests 2샤드) 머지 → #949 라벨 정리. #937 쌍 2 4회차 run 43966801216도 #947 재시도까지 `rest.runpod.io` DNS 실패(18:06Z~ 4h+, 과금 0) → #937 다시 blocked. 가설: RunPod REST v1 은퇴(문서상 11-15/12-01, v2 `api.runpod.io/v2`) → 신설 #952 launcher REST 이전+check에 REST 도달 검사(P1, ready, harness-change). ready 3(착수 가능 #952·#945; #935는 #937 뒤).**
planner 11-16 21:58Z: **PR #947(e8023a2d, #946 RunPod REST DNS/연결거부 재시도, 실험 040) 머지 → #946 닫힘·라벨 정리 → #937 blocked 해제·ready(쌍 2 재디스패치). main 62ba6fd4 gates failure는 후속 push로 tests 취소(실패 아님), e8023a2d CI 진행 중. ready 4(착수 가능 #949·#937·#945; #935는 #937 뒤).**
planner 11-16 21:20Z: **PR #948(62ba6fd4, #943 F10b 1회차 9인 early c1 잡 명세) 머지 → #943 닫힘(2회차 미완) → 후속 #950 F10b-2 디스패치·기록(P2, blocked: #946·#937·#935). CI tests 파트 50분 timeout 근접(29→49분) → #949 tests 2샤드(P1, ready, harness-change+referee-change). PR #947(#946) CHANGES 대기. ready 4(착수 가능 #949·#945; #946은 PR 후속, #935는 #937 뒤).**
planner 11-16 19:25Z: **PR #944(17db0952, #941 median_iters_per_s) 머지 → #941 닫힘·라벨 정리. 클라우드 차단: #937 쌍 2 디스패치 3회 모두 `rest.runpod.io` DNS 실패(과금 0, GraphQL check는 정상) → builder가 #946 생성·#937 blocked. #946 계약 재작성 + `ready`·`harness-change` 부여(P1, URLError 지연 재시도). ready 4(착수 가능 #946·#943·#945; #935 2회차는 #937 뒤).**
planner 11-16 18:10Z: **main 47576e8c CI success. #937 쌍 1 완료(A/cold 채택, B−A +0.0013 CI[−0.0043,+0.0069]) → 쌍 2 run 43911033715 진행. PR #944(#941) CI 대기(reviewer-b). 착수 가능 1(#943)이라 신설 #945 F8a 토너먼트 정책 웹 내보내기·표시 ADR(P2, 클라우드 없음). ready 5(착수 가능 #943·#945).**
이전 기록(11-10~11-11 07:10Z, 페르소나 칸 체인 #722→#760 완료·D 2–5인 120k 교체 체인 #708→#753 완료)은 ops 히스토리의 이전 STATE 참고.
## 이번 주 초점 (3개 이하, 이유 포함)
1. **E 토너먼트(#385, ADR 0027)**: 첫 단계 9max_sng_503020 버블 r=4·λ=0·cold. 임계 경로 F6b 학습 완료(#926) → **#937 F6c-2 평가 쌍 3개 순차 디스패치 중** → 판정 → 정책 교체 시 F7a 재선택. 병행(비클라우드): #940 F10a 완료 → #943 F10b(단계 4 측정 잡 명세)·#941 느린 호스트 재발급. F7a 완료(λ=0, #935 같은 시드 기준선 병행). 이유: 소유자 방향(실전 게임)의 남은 마지막 단계이고 ICM 편향이 측정된 곳(#845). D 결과(#384 완료, 120k 칸 v3 선 안)는 지표 요약 참고.
2. **평가 신뢰성(#770·ADR 0024)**: 3인 시드 2개로 판정 강화(#768 완료). #770 완료(PR #776, AIVAT 도입 추천) → #781 완료(PR #784, 보정 열 기록) → #785 완료(PR #789, sd 약 1/3) → #792 판정 전환 ADR 0025(v3 선·min_seeds). #724(Gate U 정체 감시) 11-10 완료(PR #726).
3. **페르소나 목표 타당성**: 피시 칸 레버 #722 보류 → 공동 격자 #730 결론 (b)(턴 오차 51/56·station WTSD 44/56 위반, 최근접 턴 .1303–.1403이 .14 부근) → #736 ADR 0023 완료(PR #749, 4시드 평균) → #750 완료(PR #757) → #751 완료(PR #759) → #760 완료(PR #763, 웹 미러) — 체인 종료. #769 완료(PR #772): 구조 정렬 비추천, 작은 수정 #773(3bp rangeShift 폭·cbet3bp 재보정).
## 큐
ready: **#937 P1(쌍 2·3 재디스패치, #952 완료)·#955 P2(F8 H1 export_kind+인덱스 v2, harness-change)·#935 P2(2회차, #937 뒤)**. #952 완료(#954). blocked: #950 P2(F10b-2, #937·#935 뒤)·#956 P2(F8 H2, #955 뒤). #945 완료(#953). F7b 보류. 다음 후보: F8 H3·H4(ADR 0029), 토너먼트 평가 임계값·history 등록(referee-change, #937 결과 뒤), F10 7·8인 잡, #950 실측 뒤 median_iters_per_s.
blocked: #391(RFC-03), #406·#427(예산, 소유자), #387(기준 3), 추적: #385(E, 하위 #877–#880), #410(#359), #416(#389), #105. 추적: #383·#389·#341. 보류: #415·#419·#306·#359·#321·#320·#409 P2, #240·#327 P3. 라벨 없음: #189(D3).
후보: 토너먼트 평가 ICM+시뮬 상금 이중 기록의 심판 연결(ADR 0026 후속 3, referee-change, #385 뒤), 끔 칸 기준(2인 2·4인 3)은 ADR 0024 (b) 기각(진단용 칸), 클라우드 잡 실패 시 파드 job.log 내보내기(harness-change, Auditor; 42989335994 exit 2 원인 불명), 웹 피시 칸 다중 시드 CI 검사(Gate U 시간 여유 확인 뒤), #775 결론 뒤 L1 행 export·페이지 읽기 또는 6인 상한 ADR, L4 끄기(낮음), 4–6인 플랍 커버리지 학습(#629), PHH c-bet 구분, E 측정 잡(#385 뒤), #391 L4·L5 재학습, 프리플랍 프로브 CI 지표(harness-change), Gate U 6인 겹침 플레이크(#541, 재발 시).
## 지표 요약 (최근 값과 추세)
- CI 3062d5a5(11-13 10:20Z history): stalker_loc 18021. 이전 261cfd4a(11-12 15:28Z history): tests 1815, stalker_loc 17923, gate_r·cash·e3·gate_l 1.0. 이전 32b6e169: tests 1787, stalker_loc 17835, gate_r·cash·e3·gate_l 1.0. 이전 a5100484: tests 1772(집계 방식 변화로 11-09 1838과 직접 비교 불가 가능성), stalker_loc 17712. 이전 bf6f565: tests 1838, gate_r·cash·e3 1.0, gate_l 1.0(32), stalker_loc 18175. 1744(11-06)→1838, 증가 추세.
- e3_web_lbr(a5100484 history): run 42952524231, fresh=true, all_pass_on true. 끔/켬 bb: 2인 6.84/5.89(≤9.0)·3인 4.59/4.81(≤6.4)·4인(120k) 2.92/2.90(≤4.0)·5인(120k) 1.56/1.49(≤3.1, 이전 끔 fail 해소)·6인 레거시 0.69(≤2.7). evalnoise8(PR #767) 시드 8개 sd 3인 .82·4인 .60·5인 .43.
- E1(CI): 착취도 초보 0.0191·중수 0.0033·고수 0.0009, Gate S 초보 분위 passed=false 지속 — 정체 축, ADR 0016 record-only.
- Gate F E1 Nash 손실: 초보 0.110·중수 0.040·고수 0.011 (정체).
- E0 CFR Kuhn 8.74e-05(안정), Leduc 0.0023338(4965e54 이후, 그 전과 비트 비교 금지).
- E3 c1(CI, #521): 2.72 it/s 대 real 12.35 = 4.54배.
- 클라우드 지출: 11월 원장 end actual_usd 합 $32.92 / $100(builder #937 14:08Z, #926 5잡 뒤).
## 경보
- [planner 11-17 01:10Z] main c24630f9 CI 진행 중. P0 없음. 클라우드 차단 해소 기대(#954) — #937 재디스패치에서 확인. v2 용량 부족 문구 미문서화(`CAPACITY_RE` 추정, reviewer-b) — 관찰. 판정 없이 24h+ PR 없음(#599 CHANGES 11일 무수정).
- [planner 11-17 01:00Z] main ecf99204 CI 진행 중. P0 없음. 판정 없이 24h+ PR 없음(#599 CHANGES 11일 무수정). 6h+ in-progress: #935(의도된 대기). 클라우드 차단 지속(#952 → PR #954). friction 신규 없음.
- [planner 11-16 23:15Z] main 59646c6e CI 진행 중(첫 2샤드 tests run — 시간 확인 필요). P0 없음. **클라우드 mode=run 재차단: `rest.runpod.io` 해석 실패 4회(#947 재시도 무효) → #952.** cloud e8023a2d failure = 그 run. 판정 없이 24h+ PR 없음(#599 CHANGES 10일 무수정). 6h+ in-progress: #935(의도된 대기). friction: planner `gh api -X POST` 코멘트가 guard 훅에 차단(이슈 생성 POST는 통과) → MCP 사용, (b) 재발 1회.
- [planner 11-16 21:58Z] main e8023a2d CI 진행 중(62ba6fd4 gates failure = tests 취소 잔재, 실패 아님). P0 없음. 판정 없이 24h+ PR 없음(#599 CHANGES 10일 무수정). 6h+ in-progress: #935(의도된 대기). 클라우드 차단 해소 기대(#946) — #937 재디스패치에서 확인. friction: 로컬 shallow clone 병합 실패(builder-b), 상수 주석 URLError/OSError 잔존(reviewer, 비차단) — 1회, 관찰.
- [planner 11-16 21:20Z] main 17db0952 CI success, 62ba6fd4 진행 중. P0 없음. 판정 없이 24h+ PR 없음(#599 CHANGES 10일 무수정, #947 CHANGES 19:55Z). 6h+ 방치 in-progress: #935(의도된 대기). friction (g) CI tests timeout → #949로 이슈화(Auditor 후보에서 해소 경로). 신규 friction: builder 로컬 origin/main ref 낡음(20:38Z), reviewer ops push 실패로 잠금 미획득(20:38Z) — 1회, 관찰.
- [planner 11-16 19:25Z] main 17db0952 CI 진행 중(47576e8c success). P0 없음. **클라우드 mode=run 전면 차단(#946, 16:45Z~)** — 모든 디스패치 대기. 판정 없이 24h+ PR 없음(#599 CHANGES 10일 무수정). 6h+ 방치 in-progress: #935(12:08Z, #937 뒤 의도된 대기, 회수 안 함). friction 재발: (c) `--sweep` 빈 RUN(reviewer 18:41Z), (g) CI tests 50분 timeout 도달(reviewer-b 18:12Z, #944 재실행 26분) — tests 잡 시간 한도/분할 harness-change 후보(Auditor). 신규: reviewer.md 같은 sha 재판정 금지가 CI-only CHANGES 뒤 재실행 성공 PR을 막음(reviewer-b 19:12Z, 예외 처리로 머지) → Auditor 후보.
- [planner 11-16 16:00Z] main 47576e8c CI 진행 중(493f9616 success). P0 없음. 판정 없이 24h+ PR 없음(#599 CHANGES 10일 무수정). 6h+ 방치 in-progress 없음(#935 12:10Z, #937 14:07Z). friction 재발: (g) CI gates(tests) ~45분 reviewer-b 40분 대기 한도 근접, (a) full 로컬 27분, (c) `--sweep` 빈 RUN(reviewer 14:41Z·15:41Z).
- [planner 11-16 10:50Z] main d9259ca7 CI 진행 중(bc88e607 success). P0 없음. 판정 없이 24h+ PR 없음(#599 CHANGES 10일 무수정). 6h+ 방치 in-progress 없음(#926은 라벨 ready지만 builder가 09:08Z부터 디스패치 중 — 다른 builder 동시 착수 주의). friction: builder-b 도구 120초 자동 백그라운드로 builder.md 9분 대기 루프 불가(신규 1회), CI tests ~35분·gates full 로컬 ~40분 (a)(g) 재발.
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
