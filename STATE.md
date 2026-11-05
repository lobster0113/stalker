# STATE (2026-11-05 11:40Z, planner)
## 현재 단계
**D2 설계·준비(주력) + 소유자 방향 전환(10-30): 실전 게임 학습. ADR 0019 순서: A real 메뉴(#382·#386 완료·#387) → B1·B2·B3(#389) ∥ S 좌석별 스택(#383) → C 결합 key c1(#400) → D 2–5인(#384) → E 토너먼트(#385).** D1 종료. NH-3·5·6·7·9·11 open(비차단). FEEDBACK.md 없음(11-01 19:10Z 확인).
planner 11-05 11:40Z: **PR #586(5d2733f, #585 export_web_policy `--players`로 mixn c1 → 인원별 파일·by_players LBR 메타) 머지** → #585 잔존 ready·in-progress 정리(반복). 신규 **#588 P2 harness-change**(cloud.yml `mode=export`: M2–M4 아티팩트 → 2–6인 웹 정책 아티팩트 + `ops:cloud/exports/`, 아티팩트 만료 ~12-03 전). 열린 PR #587(#579, reviewer CHANGES: stale base 충돌). main CI 5d2733f 진행 중, b312fc1 success.
planner 11-05 10:20Z: **PR #584(b312fc1, #583 웹 c1 key 미러 `publicKeyC1` + 2·4·6인 패리티 벡터) 머지** → #583 잔존 ready·in-progress 정리(반복). 신규 **#585 P2**(export_web_policy `--players`로 mixn c1 → 인원별 파일, ADR 0021 후속 2 코드 절반; CI 내보내기 워크플로는 그 뒤 harness-change). 열린 PR 없음. main CI b312fc1 진행 중, 0496fb7 success.
planner 11-05 07:35Z: **PR #582(0496fb7, #581 ADR 0021: short-handed는 mixn c1 한 정책(인원 간 공유 키 0.04%), 9인 mid9 연결은 후속, 11월 실지출 $19.79) 머지** → #581 잔존 ready·in-progress 정리(반복). 신규 **#583 P2**(웹 c1 key 미러, ADR 0021 후속 1·#384 기준 3). 열린 PR 없음. main CI 0496fb7 진행 중, fbec690 success.
planner 11-05 05:15Z: **PR #578(fbec690, #576 인원별 LBR 판정 → `ops:cloud/verdicts/<job>.json` 기록 전용, 실험 032) 머지** → #576 잔존 ready·in-progress 정리(반복). #479 RECLAIM(구간 1/4 run 41884879698 20:50Z success, 다음 구간 미착수 8h). #579 builder-b CLAIM인데 in-progress 누락 → 부착. 신규 **#581 P2**(#384 종료 조건: 정책 방식·9인·계산 계획 ADR 0021). 열린 PR 없음. main CI fbec690 진행 중, 4b7dcd8 success.
planner 11-05 03:15Z: **PR #577(4b7dcd8, #566 mixn 시드 2 잡 주석 정정) 머지** → #566 잔존 ready·in-progress 정리(반복). 열린 PR #578(#576). 신규 **#579 P2**(avg_cap own·cap2·cap8 resume 3×10⁵ 재측정, #567 후속 a)·**#580 P3**(own 평균 LBR 1.20>현재 0.89 원인 조사). ready 미착수 4개(#579·#573·#569·#580). main CI 4b7dcd8 진행 중, 472ed0f success.
## 이번 주 초점 (3개 이하, 이유 포함)
1. **D 2–5인(#384)**: 평가기(#534)·인원별 값(#542)·시드 분산(#548·#559) → 합격선 ADR 0020 머지(#564) → #572 판정기 머지(c1 2–6인 pass) → #576 기록 연결 머지 → #581 ADR 0021 머지(mixn c1 한 정책) → #583 웹 c1 key 미러 머지 → #585 인원별 내보내기 머지 → **#588 CI 내보내기(mode=export)**, 다음: 정책 커밋 PR·서비스가 c1 정책·publicKeyC1 사용. 소유자가 크리티컬하다고 한 short-handed.
2. **C 고수 체인 비용(NH-11 (a))**: #560 gzip 머지로 큰 체인 아티팩트 한도가 풀렸다 → #479(b2 대 b1 10⁵회) 재개, b1 체크포인트 12-01 만료 전. 다음 C 재측정 때 #527 it_ratio로 CPU 맞춘 배수 보고.
3. **페르소나 턴 폴드(#533 머지 → #569)**: giveup_turn으로 턴 오차 절반(.140)이나 nit .29 잔존, 수동 스윕 한계 → 자동 탐색. 서비스 상대 모델 신뢰도에 직결. #519(PHH)에서 인간 프로 flop c-bet 52.1%가 목표보다 13%p 낮게 나와 c-bet 목표 재검토 근거가 생겼다.
## 큐
ready 미착수: #588 P2·#573 P3·#569 P3·#580 P3 (4) + #479 P2(구간 2/4 run 41991776948 08:14Z 디스패치). in-progress: #579 P2(builder-b, PR #587 CHANGES). 상태 라벨 없음: #463. #429 분할 남은 것: Python 사이즈-강도·텔·매트릭스 이식, field_v2 referee-change.
blocked: #391(RFC-03), #406·#427(예산, 소유자), #387(기준 3), #384(추적, #588), #385(엔진), #410(#359), #416(#389), #105. 추적: #383·#389·#341. 보류: #418·#415·#419·#306·#359·#264·#321·#320·#409 P2, #240·#327 P3. 라벨 없음: #189(D3)·#323(P3).
후보: #588 뒤 c1 정책 web/app/policy 커밋 PR·서비스 c1 전환, ADR 0021 후속 4 c1 9인 첫 측정·5 6인 단독 c1 같은 파드 D 배수, AIVAT field·LBR 통합+NLHE 가치 함수(#573 뒤, referee-change), 평균 LBR 평가 시드 8(#567 후속 b), 56k 반복 시드 2+(#555 후속 3), 평가 시드 분리(ADR 0020 한계), PHH c-bet 구분(#543 후속), E 측정 잡(#385 뒤), #391 L4·L5 재학습, 프리플랍 프로브 CI 지표(harness-change).
## 지표 요약 (최근 값과 추세)
- CI bea9bc8(18:12Z): tests 1590, failed 0, gate_r·cash·e3 1.0(e3 116,238), gate_l 1.0(32), stalker_loc 15527. 테스트 수 증가 추세(1524→1590, 1일).
- E1(CI): 착취도 초보 0.0191·중수 0.0033·고수 0.0009, Gate S 초보 분위 passed=false 지속 — 정체 축, ADR 0016 record-only.
- Gate F E1 Nash 손실: 초보 0.110·중수 0.040·고수 0.011 (정체).
- E0 CFR Kuhn 8.74e-05(안정), Leduc 0.0023338(4965e54 이후, 그 전과 비트 비교 금지).
- CI f0d2526(11-03 05:04Z): success, tests 1641, gate_r·cash·e3 1.0, gate_l 1.0(32), stalker_loc 16080. 1626→1641(3시간).
- E3 c1(CI, #521): 2.72 it/s 대 real 12.35(같은 시각) = 4.54배, CPU 맞춤 3.20(참고). 이전 #503 3.27배. regret 해시는 시드별로 같다.
- 클라우드 지출: 11월 원장 actual_usd 합 $19.79 / $100(ADR 0021, 이전 STATE 값 $9.45는 낡음).
## 경보
- [planner 11-05 11:40Z] PR #587(#579) stale base 51e7849에서 열려 add/add 충돌·CI 0개(reviewer 11:23Z) → builder-b는 PR 전 `git fetch origin main` 후 rebase. gates quick 300초 도구 타임아웃 초과((a), builder 11:04Z).
- [planner 11-05 10:20Z] friction (b) 재발: reviewer-b 10:16Z `gh pr merge` GraphQL 403·`gh api PUT` 훅 차단 → MCP 머지, reviewer.md §2가 아직 `gh pr merge`를 지시(지침 불일치, Auditor 후보). 머지된 브랜치 삭제 경로 없음(#105). 아티팩트 zip 403 → 로컬 e2e 대체 ~10분.
- [planner 11-04 21:15Z] 신규: squash 머지 PR #567 본문 `Closes #530`인데 이슈가 열린 채 남음(MCP 머지 경로 의심) → planner가 머지 뒤 연결 이슈 상태 확인. friction 지속: gates quick 로컬 1032~1190초((a), builder·builder-b 18:42·20:50Z), gh merge GraphQL 403 → MCP((b), reviewer·reviewer-b 18:44·19:25Z), 라벨 이벤트 취소 run의 stale gates 체크((d'), reviewer 17:41·20:57Z). #536은 #571 머지로 대체되어 23:30Z 닫음. #537도 Closes 후 ready·in-progress 라벨 잔존(머지 경로가 라벨을 안 지움, 반복).
- [planner 11-04 17:30Z] friction 재발: reviewer-b 17:18Z `gh pr merge` GraphQL 403·REST 훅 차단 → MCP 머지((b), 오늘 3회+). builder-b 16:55Z·builder 16:49Z gates quick 1219·1296초((a)), PR #568 후속: 느린 테스트 slow 마커 점검 후보.
- [planner 11-04 16:10Z] friction 반복: reviewer 14:28Z `gh pr merge` GraphQL 403 + REST merge 훅 차단 → MCP로 MERGE-RETRY 14:42Z((b), reviewer.md에 MCP 머지 도구 명시 후보). #536: cancelled run 실패로 내린 같은 sha CHANGES가 재판정 불가로 정체(reviewer-b 14:16·15:20Z, 11-03 14:05Z 경보와 같은 주제 3회+). `--sweep` parity 무시 RUN((h), reviewer 12:42·15:41Z).
- [planner 11-04 13:15Z] **friction 3회+ (area:harness 후보, Auditor 결정)**: guard 훅(`python harness/hooks/guard_bash.py`)이 상대 경로라 `cd web/e2e` 뒤 Bash 전체가 막힘 → builder-b #552 푸시 3회 실패(reviewer-b 10:11·11:15·12:20Z, PR #552 본문). 훅 명령을 절대 경로(`$CLAUDE_PROJECT_DIR`)로 바꾸는 harness-change 후보. 웹 e2e 9분+·Gate U 로컬 560초 한도 초과(builder-b·reviewer-b 12:30·13:05Z) → 백그라운드+폴링.
- [planner 11-03 14:05Z] 신규 friction(reviewer 13:58Z): 무관한 flaky 실패 뒤 같은 sha 재실행은 기존 VERDICT 때문에 재판정이 안 된다 → 새 커밋 필요. builder 13:06Z: `pkill -f referee.gates`가 자기 셸도 죽임. gates 로컬 1211~2120초((a) 지속).
- [planner 11-03 11:40Z] friction 재발: gates quick 1188~1254초(builder·builder-b 10:43Z, (a)), GraphQL 403·훅 차단 → MCP(reviewer-b 11:30Z, (b)), 수용 기준 경로 `training/<job>/<run>.json` ≠ 실제 `cloud/results/`(planner 이슈 작성 오류, #548부터 수정).
- [planner 11-03 09:25Z] friction 재발: docs-only #545도 로컬 gates quick ~19분, 첫 pip install이 120초 도구 타임아웃에 잘림(builder-b 08:51Z, (a)); gh GraphQL 403 → MCP 우회(reviewer 09:19Z, (b)); 대체된 cancelled run의 빨간 gates 체크((d)).
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
