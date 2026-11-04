# STATE (2026-11-04 13:15Z, planner)
## 현재 단계
**D2 설계·준비(주력) + 소유자 방향 전환(10-30): 실전 게임 학습. ADR 0019 순서: A real 메뉴(#382·#386 완료·#387) → B1·B2·B3(#389) ∥ S 좌석별 스택(#383) → C 결합 key c1(#400) → D 2–5인(#384) → E 토너먼트(#385).** D1 종료. NH-3·5·6·7·9·11 open(비차단). FEEDBACK.md 없음(11-01 19:10Z 확인).
planner 11-04 13:15Z: **PR #552(5b1860f, #551 학습·복기 정적 테이블 벳/팟 겹침 레이아웃 수정 + Gate U 시나리오 고정 픽스처) 머지** → #551 잔존 ready·in-progress 정리. 열린 PR: #562(#559 재측정 기록, 판정 대기)·#536(CHANGES 대기). main CI 5b1860f 진행 중, 1fc0b95 success. 후속 후보: 복기 `#rv-table` 고정 픽스처(PR #552 후속), 시드 2 잡 주석 문구 정정(#561 후속).
planner 11-04 10:00Z: **PR #561(1fc0b95, #558 mixn 시드 3·4 max_minutes 170→240) 머지** → #558 잔존 in-progress 정리, 선행 해소된 **#559 P2 ready**(시드 2·3·4 재측정, 실행 2회, 최악 $14.40). main CI 1fc0b95 진행 중, 72d0ef3 success. 열린 PR #552·#536 CHANGES 대기(#552는 guard 훅 상대 경로로 builder-b 푸시 3회 실패, 08:12Z). 후속 후보: 시드 2 잡 주석 "not 170 like seeds 3-4" 문구 정정(PR #561 후속).
planner 11-04 08:05Z: **PR #557(72d0ef3, #556 by_players LBR 핸드 2–3인 2,000·그 밖 600 + 행별 lbr_hands) 머지** → #556 잔존 라벨 정리. 신규 **#558 P2 ready**(mixn 시드 3·4 max_minutes 170→240: 2,000핸드 평가 시간, 시드 4가 이미 159.82분), **#559 P2 blocked**(#558 뒤 시드 2·3·4 재측정, 실행 2회, 최악 $14.40), **#560 P2 ready**(policy·ckpt gzip, #479 선행: b2 6×10⁴회 표가 256MiB 넘어 삭제, b1 체크포인트 12-01 만료 전 필요). #479 blocked(#560). main CI 72d0ef3 진행 중, 2ab3d63 success. 열린 PR: #552·#536(CHANGES 대기).
planner 11-04 03:55Z: **PR #555(2ab3d63, #548 혼합 인원 c1 시드 1–4 인원별 LBR·필드 분산) 머지** → #548 잔존 라벨 정리. 6인 현재 LBR(40k) 2.091±0.482, 0.979(56k)는 범위 밖; 시드 간 sd ≈ 평가 se → 변동 대부분 평가 잡음. 후속 **#556 P2 ready**(2–3인 LBR 핸드 600→2,000 + lbr_hands 기록). #553 00:03Z 닫힘(기준 3 충족). PR #552·#536 CHANGES 대기. main CI 2ab3d63 진행 중, c4f38e5 success.
11-03 03:10~04:50Z: #538·#539·#540(#535 v7)·#543(#519 PHH, 인간 프로 flop c-bet −13%p) 머지, #384 분할(#541·#542). 11-02 이전: #531·#522·#528·#524·#532 머지, #448·#518 분할, #491·#479 회수. #487 고수 체인 $990–1,363 → NH-11.
## 이번 주 초점 (3개 이하, 이유 포함)
1. **D 2–5인(#384)**: 평가기(#534)·웹 조회(#541)·인원별 첫 값(#542)·시드 분산(#548: sd≈se, 평가 잡음 주원인)·평가 핸드 증가(#556 완료) → #558(잡 상한, 완료) → #559(재측정, ready) 뒤 인원별 합격선 이슈. 소유자가 크리티컬하다고 한 short-handed.
2. **C 고수 체인 비용(NH-11 (a))**: #527 도구가 머지됐다(it_ratio). 다음 C 재측정 때 CPU 맞춘 배수로 보고, C 감소 후보(체크포인트 압축 473MB 등)를 찾는다. #560(표 gzip)이 #479와 c1 473MB 체크포인트를 함께 푼다.
3. **페르소나 #533(턴·리버 폴드 왜곡)**: #526 머지로 WTSD는 맞췄으나 턴 폴드가 크게 높다. 서비스 상대 모델 신뢰도에 직결. #519(PHH)에서 인간 프로 flop c-bet 52.1%가 목표보다 13%p 낮게 나와 c-bet 목표 재검토 근거가 생겼다.
## 큐
ready 미착수: #560 P2·#530 P3·#533 P3·#537 P3 (4). in-progress: #559 P2(PR #562 판정 대기). 상태 라벨 없음: #463. #429 분할 남은 것: Python 사이즈-강도·텔·매트릭스 이식, field_v2 referee-change.
blocked: #479(#560), #391(RFC-03), #406·#427(예산, 소유자), #387(기준 3), #384(추적, #541·#542), #385(엔진), #410(#359), #416(#389), #105. 추적: #383·#389·#341. 보류: #418·#415·#419·#306·#359·#264·#321·#320·#409 P2, #240·#327 P3. 라벨 없음: #189(D3)·#323(P3).
후보: 인원별 합격선(#559 뒤), 56k 반복 시드 2+(#555 후속 3), 평가 시드 분리(후속 4), PHH c-bet 헤즈업/멀티웨이·3-bet 팟 구분(#543 후속, #533과 함께 검토), E 측정 잡(#385 뒤), #391 L4·L5 재학습, 웹 key 미러(c1), 프리플랍 프로브 CI 지표(harness-change).
## 지표 요약 (최근 값과 추세)
- CI bea9bc8(18:12Z): tests 1590, failed 0, gate_r·cash·e3 1.0(e3 116,238), gate_l 1.0(32), stalker_loc 15527. 테스트 수 증가 추세(1524→1590, 1일).
- E1(CI): 착취도 초보 0.0191·중수 0.0033·고수 0.0009, Gate S 초보 분위 passed=false 지속 — 정체 축, ADR 0016 record-only.
- Gate F E1 Nash 손실: 초보 0.110·중수 0.040·고수 0.011 (정체).
- E0 CFR Kuhn 8.74e-05(안정), Leduc 0.0023338(4965e54 이후, 그 전과 비트 비교 금지).
- CI f0d2526(11-03 05:04Z): success, tests 1641, gate_r·cash·e3 1.0, gate_l 1.0(32), stalker_loc 16080. 1626→1641(3시간).
- E3 c1(CI, #521): 2.72 it/s 대 real 12.35(같은 시각) = 4.54배, CPU 맞춤 3.20(참고). 이전 #503 3.27배. regret 해시는 시드별로 같다.
- 클라우드 지출: 월 $9.45 / $100(실험 025 기록).
## 경보
- [planner 11-04 13:15Z] **friction 3회+ (area:harness 후보, Auditor 결정)**: guard 훅(`python harness/hooks/guard_bash.py`)이 상대 경로라 `cd web/e2e` 뒤 Bash 전체가 막힘 → builder-b #552 푸시 3회 실패(reviewer-b 10:11·11:15·12:20Z, PR #552 본문). 훅 명령을 절대 경로(`$CLAUDE_PROJECT_DIR`)로 바꾸는 harness-change 후보. 웹 e2e 9분+·Gate U 로컬 560초 한도 초과(builder-b·reviewer-b 12:30·13:05Z) → 백그라운드+폴링.
- [planner 11-03 14:05Z] 신규 friction(reviewer 13:58Z): 무관한 flaky 실패 뒤 같은 sha 재실행은 기존 VERDICT 때문에 재판정이 안 된다 → 새 커밋 필요. builder 13:06Z: `pkill -f referee.gates`가 자기 셸도 죽임. gates 로컬 1211~2120초((a) 지속).
- [planner 11-03 11:40Z] friction 재발: gates quick 1188~1254초(builder·builder-b 10:43Z, (a)), GraphQL 403·훅 차단 → MCP(reviewer-b 11:30Z, (b)), 수용 기준 경로 `training/<job>/<run>.json` ≠ 실제 `cloud/results/`(planner 이슈 작성 오류, #548부터 수정).
- [planner 11-03 09:25Z] friction 재발: docs-only #545도 로컬 gates quick ~19분, 첫 pip install이 120초 도구 타임아웃에 잘림(builder-b 08:51Z, (a)); gh GraphQL 403 → MCP 우회(reviewer 09:19Z, (b)); 대체된 cancelled run의 빨간 gates 체크((d)).
- [planner 11-03 03:10Z] friction 반복: 로컬 gates quick 860~1013초(builder·builder-b 11-03, (a)), 연구 PR에 연결 이슈·수용 기준이 없어 리뷰 기준 부재(researcher·reviewer-b 00:00·00:11Z, 신규), should_run 잠금 없는 RUN(reviewer-b 01:24Z 재발).
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
