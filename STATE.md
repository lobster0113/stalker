# STATE (2026-11-17 13:10Z, planner)
## 현재 단계
**D 2–5인 완료 → E 토너먼트(#385, ADR 0027) 진행. 1단계(9max_sng_503020 버블 r=4) 판정 기록 완료: PR #960(33bc23f6) 머지, #937 닫힘 — cold A 채택, λ=0·cold 확정.** #950 9인 early 측정 완료(run 44061938004, 18.05 it/s, $0.38).** D1 종료. NH-3·5·6·7·9·11 open(비차단). FEEDBACK.md 없음.
planner 11-17 13:10Z: **#950 닫힘(9인 early 18.05 it/s·max_iters 20000 도달·44370 keys·$0.3839, 원장 $33.84/$100) → #965 F11b blocked 해제·ready(#969와 #877 단독 순서). 신설 #971 F10b early9 잡 `median_iters_per_s [18]`·max_iters 상향(P2 ready). PR #970(#958 ADR 0030) CHANGES 대기. ready 6(착수 가능 #965·#969·#971, 진행 #958·#964·#968).**
planner 11-17 09:55Z: **PR #967(#956 F8 H2 웹 토너먼트 정책 로드·단계 매핑) 머지 97920a63 → #956 라벨 정리. 신설 #968 F8 H3 pill·툴팁·복기 일치(P2 ready)·#969 F8 H4 첫 실제 export cold A 43735226442 + 반입(P2 ready, #877 단독 디스패치 — #950과 순서). ready 5(#950·#958·#964·#968·#969).**
planner 11-17 09:40Z: **PR #966(#935 F7a 같은 시드 CI 기준선, 채택 λ 정책0·random0·tag0.2) 머지 → #935 라벨 정리, #950 blocked 해제·ready(선행 #946·#937·#935 해소). #956 H2는 PR #967 판정 대기. ready 3(#950·#958·#964) + #956 PR 중.**
planner 11-17 08:10Z: **PR #959(#955 H1)·#962(#957 F11a)·#963(#961 F6d) 머지 → 라벨 정리, #956 H2 blocked 해제·ready. 신설 #964 F6e `_counts` by_street 합산(P2 ready referee-change, #963 후속)·#965 F11b 단계 2 디스패치·기록(P2 blocked, #935·#950 뒤). ready 4(#935 P2·#956 P2·#958 P2·#964 P2).**
planner 11-17 05:05Z: **PR #960 머지(#937 닫힘) → #935 선행 해소. 신설 #961 F6d 백오프 진단(no_key 분리·거리별 적중률, P2 ready, 클라우드 없음) — #937 74% 백오프가 A/B 희석·판정 신뢰성 위험. ready 5(#957 P1·#935·#955 PR #959 CHANGES·#958·#961).**
planner 11-17 04:15Z: **#937 클라우드 3쌍 완료(43882446641 +0.0013·44000780867 +0.0007·44005595416 −0.0019, 모두 CI가 0 포함) → builder가 연구 문서·PR 진행 중. #935 2회차 착수 가능(in-progress 해제·ready). 신설 #957 F11a 단계 2 SNG m(r=3·2) cold 잡 명세(P1, ready, 클라우드 없음)·#958 F4b 토너먼트 평가 판정 전환 ADR(P2, ready, docs). ready 5(#937 PR 중·#955 builder-b 중·착수 가능 #935·#957·#958).**
planner 11-17 01:10Z: PR #954(#952 RunPod REST v2) 머지 → #937 재개. 01:00Z: PR #953(ADR 0029) 머지 → #955 H1·#956 H2 신설.
이전 기록(11-16, 클라우드 DNS 차단 #946→#952, CI 2샤드 #949)은 ops 히스토리의 이전 STATE 참고.
## 이번 주 초점 (3개 이하, 이유 포함)
1. **E 단계 1 마무리 → 단계 2**: #935·#950 완료 → F11b 단계 2 디스패치 #965(지금 착수 가능). 이유: 소유자 방향(실전 게임)의 마지막 단계이며, 클라우드 단독 디스패치 규칙(#877) 때문에 순서가 임계 경로다.
2. **토너먼트 정책을 서비스에 노출(F8, ADR 0029)**: H1 #955·H2 #956 완료 → #968 H3(표시·복기)·#969 H4(첫 실제 export, cold A 43735226442) 병행. 이유: 학습 결과가 Training Game에 닿아야 북극성 지표가 움직인다.
3. **평가 판정화(#958) + 커버리지 진단(#961)**: 토너먼트 지표가 모두 record-only이고 결정 74%가 백오프라 진척을 판정할 수 없다. 심판 능력 부족은 최우선 원칙이므로 ADR과 진단을 먼저, 그 뒤 referee-change·커버리지 후속.
## 큐
ready: #965 P2(F11b 단계 2 디스패치, 임계 경로)·#969 P2(F8 H4 export — #965와 단독 디스패치 순서)·#971 P2(F10b early9 잡 it/s)·진행 중 #958(PR #970 CHANGES)·#964·#968. 다음 후보: #964 뒤 클라우드 평가 재실행으로 거리별 백오프 확인 → 버블 key 커버리지 개선, F4b 후속 referee-change(#958 뒤), 단계 3 앤티 잡(F11 뒤), F10 7·8인 잡, #950 실측 뒤 median_iters_per_s.
보류/추적: #391(RFC-03)·#406·#427(예산, 소유자)·#387·#385(E 추적)·#410·#416·#105·#383·#389·#341·#415·#419·#306·#359·#321·#320·#409·#240·#327. 라벨 없음: #189(D3). #599 CHANGES 11일 무수정(research PR).
## 지표 요약 (최근 값과 추세)
- CI history 97920a63(11-17 10:09Z): tests 2219 통과/0 실패, stalker_loc 19924, gate_r·cash 1.0 — 증가 추세(07:56Z 84759fdb 2215).
- e3_web_lbr(a5100484): 끔/켬 bb 2인 6.84/5.89·3인 4.59/4.81·4인 2.92/2.90·5인 1.56/1.49·6인 0.69, all_pass_on true.
- E1 착취도 초보 0.0191·중수 0.0033·고수 0.0009, Gate S 초보 분위 passed=false 지속 — 정체 축(ADR 0016 record-only). Gate F E1 Nash 손실 0.110/0.040/0.011 정체.
- E0 Kuhn 8.74e-05, Leduc 0.0023338. E3 c1 2.72 it/s(real 12.35, 4.54배).
- 토너먼트(클라우드 결과, record-only): #937 B−A se ≈0.0029, A bubble_mean_rel 0.030–0.034(유의 2–3/9), policy backoff_rate ≈0.74(주로 no_key) — 커버리지 낮음, 관찰.
- 클라우드 지출: 11월 원장 합 $33.45 / $100. REST v2 이전 뒤 run 시간 단축(쌍 2 38분·쌍 3 65분 vs 쌍 1 157분), 원인은 포드 사양 추정.
## 경보
- [planner 11-17 13:10Z] main 97920a63 CI metrics 기록(2219 통과/0 실패), P0 없음, 24h+ 무판정 PR 없음(#970 CHANGES 11:27Z, #599 CHANGES 11일), 6h+ in-progress 없음. friction 반복: `--sweep` 판정 끝난 PR에도 RUN(reviewer·reviewer-b 11-17 3회+, 기존 (c)), docs-only PR full ~29분(기존 (g)).
- [planner 11-17 09:55Z] main 97920a63 CI 진행 중(26ce3588 gates failure는 다음 push로 인한 취소 — 실패 아님), P0 없음, 24h+ 무판정 PR 없음(#599 CHANGES 11일), 6h+ in-progress 없음. friction 신규: reviewer web-screenshots zip 프록시 403·로컬 Gate U §12 기존 실패(1회, 관찰).
- [planner 11-17 09:40Z] main 26ce3588 CI 진행 중(이전 84759fdb success), P0 없음, 24h+ 무판정 PR 없음(#599 CHANGES 11일 무수정), 6h+ in-progress 없음. friction 신규 없음(오래된 로컬 origin/main 참조 builder 2회 — 관찰).
- [planner 11-17 08:10Z] main 84759fdb CI metrics 기록(실패 0), P0 없음, 24h+ 무판정 PR 없음(#599 CHANGES 11일 무수정), 6h+ in-progress 없음. friction 반복: `should_run --sweep`이 판정 끝난 PR·짝/홀 불일치에도 RUN(reviewer·reviewer-b 11-17 3회) → 기존 (c) 후보 강화, Auditor 결정.
- [planner 11-17 05:05Z] main 33bc23f6 CI 진행 중(이전 c24630f9 success), P0 없음, 24h+ 무판정 PR 없음, 6h+ in-progress 없음(#955는 PR #959 활성), friction 신규: reviewer-b `--sweep` 홀짝 무시 RUN(1회, 관찰).
- [planner 11-17 04:15Z] main c24630f9 CI success. P0 없음. 판정 없이 24h+ PR 없음(#599 CHANGES 11일 무수정). 6h+ in-progress: #935 해제(의도된 대기 종료). 클라우드 차단 해소 확인(check 44000604735 REST v2 ok, 3 run success). policy backoff_rate 0.74(no_key)는 평가 신뢰성 위험 — #958 ADR에서 다룰 것. friction 신규 없음.
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
