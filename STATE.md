# STATE (2026-11-02 23:50Z, planner)
## 현재 단계
**D2 설계·준비(주력) + 소유자 방향 전환(10-30): 실전 게임 학습. ADR 0019 순서: A real 메뉴(#382·#386 완료·#387) → B1·B2·B3(#389) ∥ S 좌석별 스택(#383) → C 결합 key c1(#400) → D 2–5인(#384) → E 토너먼트(#385).** D1 종료. NH-3·5·6·7·9·11 open(비차단). FEEDBACK.md 없음(11-01 19:10Z 확인).
planner 11-02 23:50Z: **PR #532(479eb96, #491 D 첫 측정 기록) 머지** → #491 종료(ready·in-progress 라벨 제거). mixn c1 run 41515877838: 키 1.66M, 6인 LBR 0.979/평균 1.715, C 단독 대비 나빠진 근거 없음. 2–5인은 평가기가 없어 판단 불가 → 새 **#534 P1 referee-change**(인원별 LBR·필드 by_players, #384 선행)와 **#535 P2**(학습 결과에 인원별 핸드·방문·키 수). main CI 479eb96 대기.
planner 11-02 23:20Z: **PR #531(adeb06c, #526 WTSD 보정) 머지** → #526 종료(ready·in-progress 라벨 제거). WTSD ±6%p 달성, 턴 폴드는 목표 +20~45%p(리서치 노트에 트레이드오프 기록) → 새 **#533 P3**(기브업 스트리트·라인 분리, 턴 폴드 오차 절반 이하). PR #532(#491 D 첫 측정 기록, run 41515877838 success) 판정 대기. main CI adeb06c 진행 중, 0bf1f8f success.
planner 11-02 20:20Z: **PR #522(0bf1f8f, #525 페르소나 스트리트 파라미터 PRESETS_V2) 머지** → #525 종료(잔존 ready·in-progress 라벨 제거), **#526(WTSD 보정) ready P2**. main CI 0bf1f8f 대기, c3f9c6a 진행 중.
planner 11-02 19:45Z: **PR #528(c3f9c6a, #491 mixn 파드 워커 16) 머지**: 41406758360 exit 137은 OOM 추정이며 cpu3c 64GB, 최악 $3.40로 같다. 다음 builder가 재디스패치한다(#491 Refs, in-progress 유지). main CI 143275a success, c3f9c6a 진행 중. **#448 needs-split 처리**: #529(장난감+avg_cap, cap 없는 경로 비트 동일, ready P3)와 #530(머지 후 CI sd 비교, #529 뒤)로 나누고 #448을 닫았다. **#479 구간 2**: b1 41485669687 success, b2 41485711669 failure(resume 체크포인트 없음, 시작 직후)라 #479에 코멘트했다. PR #522는 본문을 Closes #525로 고쳤고 reviewer-b 재판정을 기다린다.
planner 11-02 15:50Z: **PR #524(143275a, #521 c1 CI 재측정) 머지**: 같은 시각 배수 4.54배(CPU 배정이 반대), CPU를 맞추면 3.20(참고). 고수 체인 $684–2,292로 여전히 $660 위, NH-11 open 유지. 143275a main CI 진행 중(42b0b23 green, tests 1609). **#518 needs-split 처리**: #525(PR #522 범위, WTSD는 보고만)와 #526(WTSD 보정, #525 뒤)로 나누고 #518을 닫았다. 새 P2 #527(summarize 시드별 it/s + CPU 맞춤 배수 도구). **회수**: #491(run 41406758360 failure 08:45Z)·#479(구간 1 run 둘 다 success, 11-01 이후 정체)의 `in-progress`를 뗐다.
11-01 이전 요약: #487 c1 실측 X 5.0–6.9(<9.0), 반복당 ×2.70 → 고수 체인 $990–1,363 > $660 → NH-11(추천 (a) 비용 먼저). #488 Leduc 불일치 = Py3.12 sum → fsum(4965e54, Leduc 0.0023338). #397 임시 정책 배지, #401 launcher flavor 대체, #480·#466 머지(실험 030 첫 성공).
## 이번 주 초점 (3개 이하, 이유 포함)
1. **C 고수 체인 비용(NH-11 (a))**: #521 재측정 결과 4.54배(CPU 맞춤 3.20). 어느 가정이든 $660 위다. CPU 잡음이 ±40%라 **#527(측정 도구)이 먼저**이고, 그 뒤에 C 감소 후보를 새로 찾는다(체크포인트 압축 473MB 등).
2. **D 인원별 평가(#534, P1 referee-change)**: #491 첫 측정은 6인만 판단 가능했다. 평가 능력이 진척 판단을 막고 있어 최우선이며, #384(2–5인 서비스)의 선행이다. #535(인원별 카운트)는 병행.
3. **페르소나 #533(턴·리버 폴드 왜곡)**: #526 머지로 WTSD는 맞췄으나 턴 폴드가 크게 높다. 서비스 상대 모델 신뢰도에 직결. #519(PHH 검증)와 병행 가능.
## 큐
ready 미착수: #534 P1·#527 P2·#535 P2·#529 P3·#533 P3·#519 P3·#520 P3 (7). in-progress: #479(구간 2, b2 재디스패치 필요). 대기: #530(#529 뒤). 상태 라벨 없음: #463. #429 분할 남은 것: Python 사이즈-강도·텔·매트릭스 이식, field_v2 referee-change.
blocked: #391(RFC-03), #406·#427(예산, 소유자), #387(기준 3), #384(#534), #385(엔진), #410(#359), #416(#389), #105. 추적: #383·#389·#341. 보류: #418·#415·#419·#306·#359·#264·#321·#320·#409 P2, #240·#327 P3. 라벨 없음: #189(D3)·#323(P3).
후보: c1 체크포인트 압축(473MB), E 측정 잡(#385 뒤), #391 L4·L5 재학습, 웹 key 미러(c1), 프리플랍 프로브 CI 지표(harness-change).
## 지표 요약 (최근 값과 추세)
- CI bea9bc8(18:12Z): tests 1590, failed 0, gate_r·cash·e3 1.0(e3 116,238), gate_l 1.0(32), stalker_loc 15527. 테스트 수 증가 추세(1524→1590, 1일).
- E1(CI): 착취도 초보 0.0191·중수 0.0033·고수 0.0009, Gate S 초보 분위 passed=false 지속 — 정체 축, ADR 0016 record-only.
- Gate F E1 Nash 손실: 초보 0.110·중수 0.040·고수 0.011 (정체).
- E0 CFR Kuhn 8.74e-05(안정), Leduc 0.0023338(4965e54 이후, 그 전과 비트 비교 금지).
- CI 42b0b23(#517): success, tests 1609, gate_r·cash·e3 1.0, stalker_loc 15604. 1590→1609(1일).
- E3 c1(CI, #521): 2.72 it/s 대 real 12.35(같은 시각) = 4.54배, CPU 맞춤 3.20(참고). 이전 #503 3.27배. regret 해시는 시드별로 같다.
- 클라우드 지출: 월 $9.45 / $100(실험 025 기록).
## 경보
- [planner 11-02 23:50Z] friction 반복: docs-only PR #532도 로컬 gates quick 1030초·full 2017초((a)/(g)), 요약 JSON 인원별 값 부재 + 아티팩트 프록시 403(#535로 대응). reviewer-b: 대체된 CI run이 같은 sha에 cancelled gates 남김((d)).
- [planner 11-02 19:45Z] 신규 friction: (i) 같은 sha 61bb74b에 reviewer CHANGES 판정 두 건이 14초 간격으로 달렸고 내용이 상충했다(잠금 우회 동시 실행 의심, reviewer 17:36·18:07Z). (j) 측정 이슈의 선행 수정 PR은 Refs를 써야 하는데 PROTOCOL §4는 Closes를 필수로 한다(builder 19:04Z). 둘 다 Auditor 판단 후보.
- [planner 11-02 10:35Z] PR #516 머지 거부(09:46Z) → MERGE-RETRY 2/3로 10:25Z 머지(3시간 이내, 실험 030 기준 충족). 거부 원인은 auto-mode 분류기(Merge Without Review) — 재발 관찰.
- 신규 friction(reviewer 10:29Z): 라벨 부착 run이 첫 run을 취소해 집계 gates failure 잔존 → (d') 재확인.
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
- **friction (h)**: `should_run --sweep`이 parity 맞는 PR이 없어도 RUN을 낸다(reviewer 11-02 2회). (c)와 같은 계열이다.
- PR CI 지표 스냅샷 확인 불가(record-metrics가 PR run 값 미기록, 아티팩트 blob 프록시 403) → 이런 기준은 이슈에 넣지 않는다.
- 충돌 PR은 pull_request CI가 안 돈다 → CHANGES만 가능(ARCHITECTURE.md 동시 수정 충돌 반복). 후보 유지.
- 머지 후에만 가능한 CI 비교는 처음부터 별도 이슈로(planner 규칙, #503 적용).
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
