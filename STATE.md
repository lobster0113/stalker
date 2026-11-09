# STATE (2026-11-09 12:15Z, planner)
## 현재 단계
**D2 설계·준비(주력) + 소유자 방향 전환(10-30): 실전 게임 학습. ADR 0019 순서: A real 메뉴(#382·#386 완료·#387) → B1·B2·B3(#389) ∥ S 좌석별 스택(#383) → C 결합 key c1(#400) → D 2–5인(#384) → E 토너먼트(#385).** D1 종료. NH-3·5·6·7·9·11 open(비차단). FEEDBACK.md 없음.
planner 11-09 12:15Z: **PR #706(#692 이어 학습 체인 기록) 머지(96c8631a), #692 닫힘.** 2회로 120k(`max_iters`), $3.71, 학습 중 LBR 2.44→1.22. 체크포인트 165MB>pod 상한 → 더 이어 학습 불가. 후속 #707(export·적중률, ready P1)·#708(LBR 잡·mid-6 교체 판단, blocked on #707) 생성.
## 이번 주 초점 (3개 이하, 이유 포함)
1. **D 2–5인(#384)**: s4 120k 체인 완료(#692, run 42591543123). 다음 #707 export(`mode=export`, mv 2:5,3:5,4:5,5:5,6:2)·mid-6 `web_hit_rate` → #708 c1 LBR 잡 → mid-6 교체 판단. 아티팩트 ~12-04 만료. 소유자가 크리티컬하다고 한 short-handed.
2. **평가 재현성(#705)**: #698로 웹 LBR fresh 추세 복구 완료. 다음은 "정책 변화 vs 평가 변화" 구분 — E3 결과에 평가 설정·규칙 해시(#418 분리 1).
3. **페르소나 목표 타당성**: pro·tag 플랍 칸 레버 완료(Python·웹). 다음: 피시 유형 칸 연구(#701) → 적용 → 웹 미러 — 초보 테이블 상대 모델 신뢰도.
## 큐
ready 미착수: #707 P1·#705 P2·#701 P3·#463 P3 (4). in-progress 0. 열린 PR #599(CHANGES, d723a9c, reviewer 소유, 3일 무수정). #341 P1 추적.
blocked: #708(#707), #391(RFC-03), #406·#427(예산, 소유자), #387(기준 3), #384(추적), #385(엔진), #410(#359), #416(#389), #105. 추적: #383·#389·#341. 보류: #418·#415·#419·#306·#359·#264·#321·#320·#409 P2, #240·#327 P3. 라벨 없음: #189(D3).
후보: #701 뒤 피시 칸 적용·웹 미러, #708 뒤 web/app/policy 교체(추천 시), #264 mode=collect 마무리, L4 끄기(낮음), 4–6인 플랍 커버리지 학습(#629), AIVAT LBR 통합 ADR, 평가 시드 분리, PHH c-bet 구분, E 측정 잡(#385 뒤), #391 L4·L5 재학습, 프리플랍 프로브 CI 지표(harness-change), Gate U 6인 겹침 플레이크(#541, 재발 시).
## 지표 요약 (최근 값과 추세)
- CI bf6f565(11-09 04:11Z history): tests 1838, gate_r·cash·e3 1.0, gate_l 1.0(32), stalker_loc 18175. 1744(11-06)→1838, 증가 추세.
- e3_web_lbr(9660453c): run 42593131004, **fresh=true**, all_pass_on true. 끔/켬 bb: 2인 6.87/5.56(≤9.0)·3인 4.41/4.52(≤6.4)·4인 2.90/2.86(≤4.0)·5인 3.12/2.10(≤3.1, 끔 fail)·6인 레거시 0.66/—(≤2.7). 추세 기준선.
- E1(CI): 착취도 초보 0.0191·중수 0.0033·고수 0.0009, Gate S 초보 분위 passed=false 지속 — 정체 축, ADR 0016 record-only.
- Gate F E1 Nash 손실: 초보 0.110·중수 0.040·고수 0.011 (정체).
- E0 CFR Kuhn 8.74e-05(안정), Leduc 0.0023338(4965e54 이후, 그 전과 비트 비교 금지).
- E3 c1(CI, #521): 2.72 it/s 대 real 12.35 = 4.54배.
- 클라우드 지출: 11월 원장 합 $19.79 / $100(ADR 0021).
## 경보
- [planner 11-09 12:15Z] main CI red 0: 33757de0 `gates` failure는 다음 머지(96c8631a)로 tests 잡이 취소돼 생긴 집계 체크(friction (d) 재발, 실패 아님). 96c8631a 진행 중. #599 판정 후 3일+ 무수정(reviewer CLOSE 후보, 24h+ 경보 유지). #692 회수 불필요(닫힘, in-progress 라벨 정리). friction: reviewer `--sweep` 빈 RUN((h) 재발 11-09 11:41Z), reviewer-b 라벨 변경 CI 취소((d') 재발 11-09 12:02Z), gates quick 로컬 1385초((a)), reviewer.md MCP 머지 경로((b)) — Auditor W46 후보.
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
