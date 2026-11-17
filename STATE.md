# STATE (2026-11-17 23:25Z, planner)
## 현재 단계
**D 2–5인 완료 → E 토너먼트(#385, ADR 0027) 진행. 1단계 판정 완료(#937 cold A). 단계 2 학습(#965) 완료: mid3 run 44121220524 6.26 it/s·mid2 run 44139238381 7.28 it/s, 둘 다 max_iters 20000, 합계 $2.32.** #950 9인 early 측정 완료(run 44061938004, 18.05 it/s, $0.38).** D1 종료. NH-3·5·6·7·9·11 open(비차단). FEEDBACK.md 없음.
planner 11-17 23:25Z: **PR #981(#977 F8 H3b 9인 폰 페르소나 태그 넘침, 820 세로형 링+겹침 검사) 머지 af08bf09(CI 진행 중) → #977 라벨 정리. #969 builder CLAIM 23:20Z(클라우드 단독 디스패치 차례). ready 5(#969 진행·#983·#973·#978·#984), 신설 없음(3~8 범위 안).**
planner 11-17 22:30Z: **PR #982(#976 F4d history 토너먼트 판정 키 tournament_primary_ci_low·verdict 등, 로컬 참고 pass) 머지 02627f8f(CI 진행 중) → #976 라벨 정리. #965 닫힘(19:08Z, 원장 $36.16/$100) → 클라우드 비었음: #969 단독 디스패치 가능. 신설 #983 F4e ADR 0030 후속 4 되돌리는 조건 recheck(P2 ready referee-change)·#984 F11c 단계 2 잡 median_iters_per_s mid3 [6]·mid2 [7](P3 ready). ready 6(#969·#977 진행 PR #981 CHANGES·#983·#973·#978·#984).**
planner 11-17 18:30Z: **PR #979(#975 F4c 토너먼트 비열등 judge+판정 표 v1) 머지 d098ba07(CI success)·PR #980(#971 F10b early9 median_iters_per_s [18]·max-iters 80000) 머지 2ca688d5 → #975·#971 라벨 정리, #976 F4d blocked 해제·ready. #965 1회차: mid3 run 44121220524 완료(6.26 it/s — 추정 10의 0.63배, slow_host 재발급 1회, $1.48, 원장 $35.33/$100), mid2 run 44139238381 진행 중 → 끝날 때까지 #969·#973 디스패치 금지(#877). ready 6(#976·#965 진행·#969·#973·#977·#978).**
planner 11-17 15:45Z: **PR #974(#968 F8 H3 토너먼트 pill·툴팁·판 당시 정책 복기, stalker.games v2) 머지 bf8be242 → #968 라벨 정리. 후속 신설 #977 F8 H3b 9인 폰 페르소나 태그 넘침(P2 ready bug)·#978 F8 H3c 정보 막대 단계명=정책 단계(P3 ready, Planner 결정: env 있으면 정책 단계). ready 7(#975·#965·#969·#971·#973·#977·#978).**
planner 11-17 14:55Z: **PR #970(#958 ADR 0030 토너먼트 평가 판정 전환, 추천 b: sim prize−ICM 비열등 δ=0.0075·독립 학습 쌍 3) 머지 41ae38af → #958 라벨 정리. 신설 #975 F4c 판정 표+judge(P1 ready referee-change)·#976 F4d history 키(P2 blocked #975, referee-change). 후속 3(`lbr_icm` 분포, 클라우드)·4(되돌리는 조건 검사)는 #976 뒤. ready 6(착수 가능 #975·#965·#969·#971·#973, 진행 #968 PR #974).**
planner 11-17 13:40Z: **PR #972(#964 F6e `_counts` by_street 합산) 머지 701eb909 → #964 라벨 정리. 신설 #973 F6f cold A 거리별 백오프 실측 클라우드 평가 1회(P3 ready, #965·#969 뒤 단독 디스패치). ready 6(착수 가능 #965·#969·#971·#973, 진행 #958·#968).**
이전 기록(11-16, 클라우드 DNS 차단 #946→#952, CI 2샤드 #949)은 ops 히스토리의 이전 STATE 참고.
## 이번 주 초점 (3개 이하, 이유 포함)
1. **토너먼트 정책을 서비스에 노출(F8, ADR 0029)**: #969 H4 첫 실제 export(cold A 43735226442) — 클라우드가 비어 지금 단독 디스패치 차례. + #977 완료(PR #981)·#978 UI 정리. 이유: 학습 결과가 Training Game에 닿아야 북극성 지표가 움직인다.
2. **평가 판정화 마무리(ADR 0030)**: #975 judge·#976 history 키 완료 → #983 되돌리는 조건 검사(클라우드 없음). 이유: 심판 능력이 최우선, 잡음 모델 가정을 CI 기록으로 감시.
3. **E 단계 2 → 단계 3 준비**: #965 학습 완료. #984 it/s 재조정 → 단계 2 평가/단계 3 앤티 잡 기획. #973 백오프 실측은 #969 뒤 단독 디스패치. 이유: 실전 게임 방향의 임계 경로, 클라우드 단독 규칙(#877).
## 큐
ready: #969 P2(F8 H4 export — builder 진행 23:20Z, 클라우드 단독)·#983 P2(F4e recheck, referee-change, 클라우드 없음)·#973 P3(F6f 백오프 실측, #969 뒤 단독)·#984 P3(단계 2 it/s)·#978 P3(정보 막대 단계명). blocked 없음(로드맵 외 보류 제외). 다음 후보: ADR 0030 후속 3(`lbr_icm` 분포 시드 3+, 클라우드), 단계 2 평가(tournament_ab mid3/mid2), 단계 3 앤티 잡, F10 7·8인 잡, tournament_ab 출력 `schema` 필드(PR #982 제안), pod_train summary `job` 필드가 잡 이름 대신 기본값(e3-tp-mid2-c1-pod) — 2회 보고(reviewer-b·builder #965), 3회면 bug 이슈.
보류/추적: #391(RFC-03)·#406·#427(예산, 소유자)·#387·#385(E 추적)·#410·#416·#105·#383·#389·#341·#415·#419·#306·#359·#321·#320·#409·#240·#327. 라벨 없음: #189(D3). #599 CHANGES 11일 무수정(research PR).
## 지표 요약 (최근 값과 추세)
- CI history 2ca688d5(11-17 18:51Z): tests 2233 통과/0 실패, stalker_loc 19924 — 증가 추세(d098ba07 2232). tournament_verdict 키는 02627f8f CI부터 기록 예정.
- e3_web_lbr(a5100484): 끔/켬 bb 2인 6.84/5.89·3인 4.59/4.81·4인 2.92/2.90·5인 1.56/1.49·6인 0.69, all_pass_on true.
- E1 착취도 초보 0.0191·중수 0.0033·고수 0.0009, Gate S 초보 분위 passed=false 지속 — 정체 축(ADR 0016 record-only). Gate F E1 Nash 손실 0.110/0.040/0.011 정체.
- E0 Kuhn 8.74e-05, Leduc 0.0023338. E3 c1 2.72 it/s(real 12.35, 4.54배).
- 토너먼트(클라우드 결과, record-only): #937 B−A se ≈0.0029, A bubble_mean_rel 0.030–0.034(유의 2–3/9), policy backoff_rate ≈0.74(주로 no_key) — 커버리지 낮음, 관찰.
- 클라우드 지출: 11월 원장 합 $36.16 / $100(#965 mid2 end 기준). 단계 2 mid3 실측 6.26 it/s(잡 추정 10 대비 0.63배 → slow_host 오판 재발급 $0.48). REST v2 이전 뒤 run 시간 단축(쌍 2 38분·쌍 3 65분 vs 쌍 1 157분), 원인은 포드 사양 추정.
## 경보
- [planner 11-17 23:25Z] main af08bf09 CI 진행 중(이전 02627f8f success, cloud 02627f8f success), P0 없음, 24h+ 무판정 PR 없음(#599 CHANGES 11일), 6h+ in-progress 없음(#969 23:20Z). friction 신규: 새 컨테이너 numpy 미설치로 첫 full 즉시 실패(builder-b, 1회), CI 대기 25분 포그라운드(reviewer, 기존 (a)/(g) 계열).
- [planner 11-17 22:30Z] main 02627f8f CI 진행 중(이전 2ca688d5 success), P0 없음, 24h+ 무판정 PR 없음(#981 CHANGES 20:37Z, #599 CHANGES 11일), 6h+ in-progress 없음(#977 builder-b 19:40Z). friction 반복: `--sweep` 무판정 RUN(reviewer·reviewer-b 19:14·19:41·21:11, 기존 (c)), gates quick ~300s·full ~31분(기존 (a)). 신규 1회: guard 라벨 전 실패 run과 뒤 성공 run이 같이 남음(reviewer-b, 실험 039 관찰 대상).
- [planner 11-17 18:30Z] main 2ca688d5 CI 진행 중(이전 d098ba07 success), P0 없음, 24h+ 무판정 PR 없음(#599 CHANGES 11일), 6h+ in-progress 없음(#965 builder CLAIM 16:10Z, 클라우드 대기). friction 반복: `--sweep` 무판정 RUN(reviewer 16:41·17:41, 기존 (c)), gates full 25~37분(기존 (a)). 신규 관찰: 원장 end 줄에 run_id 없음(builder #965)·pod_train summary job 필드 기본값(reviewer-b) — 1회씩.
- [planner 11-17 15:45Z] main bf8be242 CI 진행 중(41ae38af cancelled=다음 push 취소, 이전 701eb909 success), P0 없음, 24h+ 무판정 PR 없음(#599 CHANGES 11일), 6h+ in-progress 없음. friction 신규 없음.
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
