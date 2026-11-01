# STATE (2026-11-01 00:50Z, planner)
## 현재 단계
**D2 설계·준비(주력) + 소유자 방향 전환(10-30): 실전 게임 학습. ADR 0019(제안, PR #392 머지 742daae) 순서: A real 메뉴(#382·#386 완료·#387) → B1 드로우·블로커(필수)·B2·B3(#389) ∥ S 좌석별 스택(#383) → C 결합 key(#400, 전체 체인은 여기서만) → D 2–5인(#384) → E 토너먼트(#385).** 예산 중간값 약 $1,600 → NH-9(월 상한 상향) open. D1 종료, NH-3·5·6·7·9 open(비차단), FEEDBACK.md 없음(11-01 확인).
10-31 요약: #447·#413·#461·#446·#472·#481·#475 닫힘(#456·#467·#473·#474·#477·#478·#483·#484 머지). P0 #469 해결(main green). real 메뉴 레인지 B 채택. B2≈b1(2e4), B3 필드 열세·키 ×1.65(`u` 지배) → c1에서 `u`를 앞/뒤 수로 축약.
planner 11-01 00:50Z: **PR #485 머지(7a99d57, c1 결합 key)** → #400 닫음(기준 3: D #486, E는 #385 엔진 뒤). #486·#487 blocked→ready(P1). 7a99d57 push CI 결과 대기. FEEDBACK.md 없음.
(00:20Z) #488 P2 ready 생성, #397 ready, #479 다회 실행 지침 코멘트.
열린 PR: #480(#462)·#466(#373). #480·#466은 같은 sha MERGE 판정 후 머지 거부 상태 지속(#482, harness-change 부여는 Auditor).
## 이번 주 초점 (3개 이하, 이유 포함)
1. **C 결합 key 측정(#487, P1 ready) ∥ D-1 혼합 인원 딜(#486, P1 ready)**: 첫 전체 체인은 c1에서만 돈다. X 실측이 고수 체인 go/no-go(§5, X≥9.0이면 재질의).
2. **평가 신뢰(#463·#488)**: E0 Leduc이 CI·로컬 다른 값 — 지표 재현성. RL-BR 수치는 E3 보고에.
3. **머지 정체 해소(#482)**: MERGE 판정 PR 2개가 builder-b 슬롯을 막아 처리량 감소(builder-b no_work 4회). Auditor 결정 필요.
## 큐
ready 미착수: #487 P1·#486 P1·#479 P2(b2 10⁵ 체인)·#488 P2·#397 P2·#482 P1(harness). in-progress: #462(PR #480)·#373(PR #466). 상태 라벨 없음: #463·#482(harness).
blocked: #391(RFC-03), #406·#427(예산, 소유자), #387(기준 3), #401(#373), #384(#486·평가기 referee-change), #385(엔진), #410(#359), #416(#389), #105. 추적: #383·#389·#341. 보류: #448·#429·#418·#415·#419·#306·#359·#264·#321·#320·#409 P2, #240·#327 P3. 라벨 없음: #189(D3)·#323(P3).
후보: E 측정 잡(#385 엔진 뒤), D 인원별 LBR·필드(referee-change), #391 L4·L5 재학습+preflop_ev 표, S 측정 노트, 웹 key 미러(c1), referee/e2/exploiter.py:63 fsum(referee-change), 프리플랍 프로브 CI 지표(harness-change).
## 지표 요약 (최근 값과 추세)
- CI 6594843(22:49Z): tests 1524, failed 0, gate_r·cash·e3 1.0(e3 116,238), gate_l 1.0(32), stalker_loc 15241. Gate S 초보 분위 passed=false 지속.
- CI 2dbe609(11:06Z): tests 1385, failed 0, gate_r 1.0, gate_r_e3 1.0(116,238, 불균등 스택 재생 추가), gate_l 1.0(32), stalker_loc 13411.
- E1(CI): 착취도 초보 0.0191·중수 0.0033·고수 0.0009(NFP 0.0019), Gate S 초보 분위 passed=false(tv_p95 0.127, golden 11/12) 지속 — 정체 축, ADR 0016 record-only.
- Gate F E1 Nash 손실: 초보 0.110·중수 0.040·고수 0.011 (정체, 변화 없음).
- E0 CFR Kuhn 8.74e-05(안정), Leduc: 4aed777·6594843 CI 0.0023444 2회 연속(단일 값), 로컬 0.0023042와 다름 → #488. 4aed777 전후 비트 비교 금지.
- E3 파드(참고, #333·ADR 0017 §8): 고수 NUT5 2.18M회 195,084키 LBR 현재 0.466±0.189 / 평균 0.774. 필드 worst 값은 #374(머지) 이전 기록이라 재계산 전까지 신뢰 불가.
- 클라우드 지출: 월 $9.45 / $100(실험 025 기록).
## 경보
- **[auditor 11-01, W44]** 무결성 위반 0(머지 206건 모두 같은 sha MERGE, metrics는 CI만 커밋). 경계 사례 #171: 같은 sha에서 순서가 뒤집힌 run의 guard가 failure로 남았다. **최대 비용 = MERGE 판정 후 머지 거부로 정체된 PR(#466·#480)** → 실험 030 #482에 harness-change·ready 부여(builder 착수). main push ci run 60%가 cancelled. CHANGES 비율 50%. E1·Gate F는 주간 내내 평평하다(북극성 Gate A/B/C 미산출). 리포트 `reports/2026-W44.md`.
- **friction 3회+ (11-01 집계)**: (a) 장시간 CI 체인 이슈가 builder 한 실행에 안 맞음(builder 17:35·builder-b 19:21·22:21) → planner 대응: 측정 이슈는 디스패치/기록 2회 실행 전제로 작성(#487·#479 코멘트). (b) gates quick 로컬 540~846초·25분+(목표 90초, 4회) → area:harness 후보(Auditor). (c) MERGE 판정 후 머지 거부(#482).
- main CI red(ab1d186·51e7849) → P0 #469 PR #471 머지(52e310a, 정수 코드만 해시). 52e310a push CI 결과 확인 대기. 교훈: float 원바이트 digest 고정 금지; #459 머지 시 CI 확인 누락 의심(Auditor).
- **PR CI 지표 스냅샷 확인 불가**: record-metrics가 PR run 값을 ops에 안 남기고 로그·아티팩트는 프록시 차단 → "PR CI 지표를 본문에" 기준 검증 불가(reviewer #483 friction, builder #483 후속) → area:harness 후보(스냅샷을 잡 요약/로그에 출력, Auditor). planner: 그 전까지 이런 기준은 이슈에 넣지 않는다.
- **PR #466 MERGE 판정 후 squash 머지가 세션 권한 분류기에 거부**(reviewer-b 01:57Z) → 같은 sha 규칙으로 이후 실행이 모두 skip(reviewer-b friction 5회+, 10-31) → area:harness 후보(같은 sha MERGE 판정의 머지 재시도 규칙, Auditor).
- **10-30 오후 ARCHITECTURE.md·index.html 충돌로 MERGE 판정 후 머지 실패 2건(#449·#443), CHANGES 누적(#423 2회)** — 충돌 PR은 CI가 없어 reviewer는 CHANGES만 가능(reviewer friction 5회+, area:harness 후보 유지, Auditor). 스택 PR(#452가 #443 포함) → 빈 PR 발생.
- 머지 후에만 가능한 CI 비교를 수용 기준에 넣은 이슈(#447 기준 1: 2×10⁴ CI 비교) → 비하네스 PR은 CI 잡 추가 불가(reviewer-b friction). planner: 새 이슈(#460·#461)는 잡 정의까지만, 수치는 별도 이슈.
- **#382 머지는 TP.md §6 변경 → 학습·채점은 real 메뉴 기준.** 웹 라벨(#386) 머지로 메뉴 일치, v1 정책(서비스)은 여전히 임시본(#397 표시).
- **사용자 이슈 대량 유입(#383~#391, 1시간에 8건)** — 영역·종류 라벨 없음, 일부 범위 밖·선행 없음, 크기 초과. planner가 라벨만 보강, 내용은 소유자 원문 유지.
- builder-b #384 작업이 컨테이너 종료로 유실(푸시 전) → 긴 작업은 중간 WIP 푸시 권장. 원인: PreToolUse guard 훅이 상대 경로라 `cd web/e2e` 뒤 모든 Bash 실패 → area:harness 후보(`$CLAUDE_PROJECT_DIR` 절대 경로, Auditor).
- **RunPod 용량 부족: cloud.yml launch 6연속 실패(20:52~21:20Z, e3-tp-mid-pod32 RESUME 40919207457, HTTP 500 "no longer any instances available")** → 비용 0, #333·#354 체인 지연. 후보: launcher가 용량 오류 시 대체 flavor(#373 cpu5c)·지연 재시도.
- 파드 시작 실패(#361) 해결 후 동시 파드 3개 정상(실험 025, #366). 필드 worst=self5 0.0 보고가 여러 이슈·ADR에 전파됨(#374).
- **사용자가 계약 형식 아닌 ready 이슈를 직접 생성(#337·#339·#341·#352·#354·#364·#373·#374)** → planner가 재작성. 내용 보존, 기준만 검증 가능하게.
- **gh CLI 토큰 무효·GraphQL 403·guard 훅(gh api PATCH 차단)** → 전 역할 MCP 우회. 후보: 지침의 gh 예시를 MCP 기준으로.
- **Actions 아티팩트 blob 호스트 프록시 403**: reviewer가 Gate U를 로컬로 대체(#331). train.yml 결과도 같은 문제 가능 — 후보(Auditor).
- **"Closes #N" vs 실행 후 기준**(#334·#345 재발, builder friction 3회+ → area:harness 후보: planner가 머지 후 실행 기준을 별도 이슈로 쓰도록 지침 보강). #339 기준 4 "Gate R 검사 추가"가 referee-change 없이 쓰여 builder가 tests/로 우회 — planner 책임, 이후 이슈는 라벨 맞출 것: 머지 후에만 가능한 기준은 처음부터 별도 이슈로. 같은 sha 규칙 때문에 본문만 고친 PR은 재리뷰 불가(reviewer-b friction).
- **충돌 PR은 pull_request CI가 안 돈다 → 리뷰어가 되돌리기만 반복**(#340·#345, reviewer friction 3회+ 10-29) → area:harness 후보: builder가 푸시 전 main 머지 의무화·충돌 알림.
- **원장 push 충돌로 파드 run red**(40840669062, #351 이전 커밋에서 시작) — #351 이후 run은 union 병합이라 재발 여부를 실험 025 창에서 볼 것. 1MB 초과 결과 요약 게시(#358 머지).
- 동시 취소 run의 gates=failure(같은 sha), 게이트를 작업 트리에서 백그라운드로 돌리면 가짜 실패(builder friction → 별도 worktree 권장). gates full 약 20분·quick 448초(목표 90초).
- **실험 번호 동시 PR 충돌**(#369 027 중복, 010 중복 기존) → area:harness 후보(번호 예약). 라벨 추가가 중복 CI run·취소 failure 체크 남김(reviewer-b friction).
- 머지된 브랜치 삭제 도구 없음(#105, guard 훅이 push --delete 차단).
- 실험 기록 규칙 누락 쉬움, 닫힌 이슈 in-progress 잔존, PR 소유 구분 불가(같은 로그인), ARCHITECTURE.md 충돌: 후보 유지.
- **ARCHITECTURE.md 동시 머지 충돌 반복**(#431·#432·#434·#437·#438, 10-30 reviewer·builder friction 5회+) → 충돌 PR에 CI 없음 → area:harness 후보(문서 색인 분할 또는 builder 푸시 전 mergeability 확인, Auditor).
- **ready 큐 범람**: 소유자 세션이 외부 리뷰 RFC 10건을 한 번에 ready로 올림 → planner가 선행 미충족분 blocked. 선행이 열린 이슈에 ready를 붙이지 않도록 대화 세션에 권고(후보).
- NEEDS_HUMAN: NH-3, NH-5, NH-6, NH-7 open (NH-8·NH-9 resolved). 리포 상호작용 제한 2027-04-23 만료.
## 진행 중 실험 (Auditor 소유, 그대로 유지)
- **030 MERGE 판정 후 머지 재시도 (#482, ready, 11-01 부여).** 측정창: 머지 후 7일. 성공 기준: 판정 후 3시간 넘게 열려 있고 NH 항목도 없는 PR 0건, 같은 sha 정체 friction 3건 이하.
- 001 builder 자가 언블록 (#55, 10-25 머지). 측정창 11-08 종료. 중간값 no_work 16%(목표 ≤10%, 기준 24%).
- 009 planner run_on_merge: 잠정 성공(W44). 013 두 번째 리뷰어: 성공(W44, 머지 21→206). 문서에 결과 기록 대기.
- 015~020·023·024·028: 7일 창 종료, 판정 보류(다음 감사 우선). 나머지(002~008·010~012·014·021·022·025~027·029)는 측정 중. 실험 문서 30개 모두 '진행 중'으로 결과 기록 없음.
