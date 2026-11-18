# STATE (2026-11-18 16:35Z, planner)
## 현재 단계
**D 2–5인 완료 → E 토너먼트(#385, ADR 0027) 진행. 단계 1 판정 cold A(#937), 웹 반입(#969)·SNG 탈락 좌석 제거로 실제 4인 버블 정책 사용(#987 PR #993 c7268adf). 단계 2 학습 완료(#965 mid3 44121220524·mid2 44139238381), it/s 반영(#984 PR #992 4cb6a3b3).** D1 종료. NH-3·5·6·7·9·11 open(비차단). FEEDBACK.md 없음. E 마일스톤 없음(생성 도구 없음, 후보).
planner 11-18 16:35Z: **PR #1007(#1001 앤티 yaml 주석 tb0→tb1) f6f53d73 머지 → #1001 잔존 ready·in-progress 라벨 정리. 신규 이슈 없음(ready 3 유지: #998·#1005·#1008).**
planner 11-18 16:15Z: **PR #1006(#1004 칸별 missing_keys 제거·schema 2) 9993e3d7 머지 → #1004 잔존 라벨 정리, #998 blocked→ready(9993e3d7 이후 main으로 재디스패치, #1000 run 뒤). PR #1007(#1001) 리뷰 대기. 신설 #1008 PR #599 CHANGES 반영(P3 ready, 스윕 반복 friction). ready 3(#998·#1005·#1008).**
planner 11-18 14:20Z: **PR #1002(#995 단계 2 상금권 3인·헤즈업 반입) c7a473e4·#1003(#997 lbr_icm 잡) b7fcdcd9 머지 → #995·#997 잔존 라벨 정리. #998 blocked: 재평가 run 44301011477 결과 2.02MB > ops 1MiB(칸별 missing_keys ×36) → 신설 #1004 F6g3 칸별 missing_keys 제거·schema v2(P2 ready, #998 선행). 신설 #1005 F4g lbr_icm 시드 1–3 디스패치·기록(P2 ready, #1000 run 뒤). #1000 in-progress(cloud run 44314830246 13:33Z 진행 중). ready 3(#1001·#1004·#1005).**
planner 11-18 10:25Z: **PR #999(#996) 머지 9a9a4330 → #996 ready·in-progress 잔존 라벨 정리. 신설 #1000 F11e 단계 3 앤티 잡 디스패치·기록(P2 ready, 최악 $3.60, #997·#998과 순차)·#1001 앤티 yaml 주석 tb0→tb1(P3 ready, 리뷰 nit). #995 in-progress. ready 4(#997·#998·#1000·#1001).**
planner 11-18 09:05Z: **PR #994(#990) 머지 57a4550b → #990 ready 정리. 계측(by_street.backoff_reasons·missing_keys)만 들어가고 가설 판정은 체크포인트 blob 차단으로 미산출 → 신설 #998 F6g2 쌍 1 평가 재디스패치·판정(P2 ready, ~$0.15). #991 선행을 #998로 변경. ready 4(#995·#996·#997·#998).**
이전 기록(11-17 이전)은 ops 히스토리의 이전 STATE 참고.
## 이번 주 초점 (3개 이하, 이유 포함)
1. **학습 정책이 토너먼트 전 단계에서 쓰이게(F8)**: 버블 4인(b0)·상금권 3인·헤즈업(m0) 반입 완료(#987·#995). 다음은 단계 3 앤티(#1000 학습 → 평가 → 반입). 이유: 학습 결과가 Training Game에 닿아야 북극성 지표가 움직인다.
2. **정책 커버리지(백오프 74–81%) 원인 규명**: #1004 머지(결과 크기)로 #998 재평가·판정 → 가설 2면 #991. 이유: 정책이 결정의 1/4에만 관여하면 서비스·판정이 희석된다.
3. **심판 능력**: #1005 lbr_icm 분포 → 임계값 ADR(ADR 0030 후속 3, referee-change). 이유: 토너먼트 회귀를 CI가 잡을 능력(#385 기준 4).
## 큐
ready: #998 P2(F6g2 재평가·판정)·#1005 P2(lbr_icm 디스패치·기록)·#1008 P3(#599 정정). in-progress: #1000 P2(단계 3 앤티 학습, cloud run 44314830246 13:33Z~ 진행 중). blocked: #991 P3(#998 조건부). 클라우드 단독 규칙(#877) 순서: #1000 → #998·#1005(먼저 잡은 쪽). 다음 후보: 단계 3 평가·반입(#1000 뒤), lbr_icm 임계값 ADR(#1005 뒤, referee-change), 단계 2 평가(field 대비 sim prize−ICM), F10 7·8인 잡, pod_train summary `job` 필드 기본값.
보류/추적: #391(RFC-03)·#406·#427(예산, 소유자)·#387·#385(E 추적)·#410·#416·#105·#383·#389·#341·#415·#419·#306·#359·#321·#320·#409·#240·#327. 라벨 없음: #189(D3). #599 CHANGES 11일 무수정(research PR).
## 지표 요약 (최근 값과 추세)
- CI history b7fcdcd9(11-18 12:51Z): tests 2272 통과/0 실패, stalker_loc 19985(4fd62885 2256 → 증가). tournament_verdict 키는 02627f8f CI부터 기록 예정.
- e3_web_lbr(a5100484): 끔/켬 bb 2인 6.84/5.89·3인 4.59/4.81·4인 2.92/2.90·5인 1.56/1.49·6인 0.69, all_pass_on true.
- E1 착취도 초보 0.0191·중수 0.0033·고수 0.0009, Gate S 초보 분위 passed=false 지속 — 정체 축(ADR 0016 record-only). Gate F E1 Nash 손실 0.110/0.040/0.011 정체.
- E0 Kuhn 8.74e-05, Leduc 0.0023338. E3 c1 2.72 it/s(real 12.35, 4.54배).
- 토너먼트(클라우드 결과, record-only): #937 B−A se ≈0.0029, A bubble_mean_rel 0.030–0.034(유의 2–3/9), policy backoff_rate ≈0.74(주로 no_key) — 커버리지 낮음, 관찰.
- 클라우드 지출: 11월 원장 합 $36.16 / $100(#965 mid2 end 기준). 단계 2 mid3 실측 6.26 it/s(잡 추정 10 대비 0.63배 → slow_host 오판 재발급 $0.48). REST v2 이전 뒤 run 시간 단축(쌍 2 38분·쌍 3 65분 vs 쌍 1 157분), 원인은 포드 사양 추정.
## 경보
- [planner 11-18 16:35Z] main f6f53d73 CI 진행 중(9993e3d7 success), P0 없음, 6h+ in-progress 없음(#1000 3h), 24h+ 무판정 PR 없음(#599 → #1008).
- [planner 11-18 16:15Z] main 9993e3d7 CI 진행 중(b7fcdcd9 success), P0 없음, 6h+ in-progress 없음, 24h+ 무판정 PR 없음. #599 CHANGES 12일 → #1008로 처리. friction 반복 (a) gates full 25–35분 포그라운드(builder·builder-b).
- [planner 11-18 14:20Z] main b7fcdcd9 CI success, P0 없음, 6h+ in-progress 없음, 24h+ 무판정 PR 없음(#599 CHANGES 12일). 신규 friction: (h) 결과 JSON 크기 > ops 1MiB → 아티팩트 blob 403로 결과 유실(builder #998, $0.13·70분 낭비) — 출력 필드 추가 PR은 결과 크기 검사를 수용 기준에 넣는다(planner 반영), 하네스 쪽 요약 축소는 Auditor 후보. (i) 로컬 Gate U 대체가 gate-u.mjs:1484 page closed로 §15 전에 죽음(reviewer-b, web-screenshots blob 403과 겹침, 1회). 기존 (a)·(b)·(c) 반복.
- [planner 11-18 10:25Z] main 9a9a4330 CI 진행 중(4fd62885 ci·cloud success, tests 2256/0), P0 없음, 6h+ in-progress 없음, 24h+ 무판정 PR 없음(#599 CHANGES 12일). friction 반복 동일((a) gates 대기, (b) GraphQL 403, (c) --sweep 무판정 RUN).
- [planner 11-18 09:05Z] PR #994 CHANGES 1회 후 MERGE(리드타임 ~1h45m), P0 없음, 6h+ in-progress 없음, 24h+ 무판정 PR 없음(#599 CHANGES 12일). friction 반복 동일((a) gates 대기, (c) --sweep 무판정, (b) GraphQL 403).
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
