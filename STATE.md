# STATE (2026-10-28 21:15Z, planner)
## 현재 단계
**D2 설계·준비(주력).** D1 종료, NH-3 open(비차단), FEEDBACK.md 없음.
D2 종료 조건 대비: Gate R 100%(캐시·토너먼트·E3) 유지 / TP v1: #262·#263 머지(ADR 0011 초보 hand.equity=순위) / 게이트: T1~T4·Q4(E0·E1)·S v0(+ADR 0016 #302)·F v0 머지 / 비용 산정 #314(새) / 설계 ADR 0009·0011·0015·0016.
17:46Z 이후 머지: #290(PR #294), #301(#303), #262(#292), #263(#308), #302(#307), #264 기준1(#309, Part of), #143(#311: CFR-BR — 번역식이 병목 비용 2~3배 과대). 닫힌 이슈 in-progress 라벨 정리(302·301·290·263·262). #264 → ready(인수인계: cloud.yml check→dry_run→run).
열린 PR: #310(#306 FieldMCCFR, reviewer-b 담당).
## 이번 주 초점 (3개 이하, 이유 포함)
1. **#312(P0) 지표 기록 복구**: main CI record-metrics snapshot이 30분 타임아웃(run 40756796767, gates는 success). 10:03Z 이후 history 0줄 → 성능 근거(CI) 단절. 심판 능력 부족 = 최우선 규칙.
2. **D2 게이트 판별력 확장**: #313 Gate S·F를 E1m 3인으로(멀티웨이, 9인 목표). #306/PR #310 혼합 등급 필드.
3. **D2 비용 산정 #314 → NH 결정 패키지**, #264 RunPod 1회 실측(최악 $0.12).
## 큐
ready 5: #312 P0, #264 P2, #313 P2, #314 P2, #240 P3.
in-progress: #306(PR #310).
blocked: #105. 상태 라벨 없음: #189(GTO 브라우저 P1, D3).
후보(이슈화 보류): Gate Q4에 CFR-BR 직접 최적화 값 기록(#311 후속, #312 이후), e2-exploit-beginner/xbase 학습 결과 기록(train.yml 실행 후), Gate S·F 포스트플랍(E2), 커리큘럼 후속(#173 §7).
## 지표 요약 (최근 값과 추세)
- main CI 최신 history 2deeb03(10:03Z): tests 971, failed 0, gate_r 1.0(224,269), gate_r_cash 1.0, gate_r_e3 1.0(37,462), gate_l 1.0(32), stalker_loc 8975. 이후 기록 없음(#312). 87fc993 run: gates tests 12분·checks 14분 success, snapshot 30분 초과로 취소. 4106402 run in_progress.
- E2 LBR(#259 후 CI): baseline −0.159, beginner −0.244, mid −0.234 bb/hand(하한).
- E1 분위 눈금: 초보 손실 0.244 → 0.018 bb/hand(노트). S v0 고수 분위 ADR 0016 기준으로 경계 통과(record-only).
- E0 CFR-BR(#311, 로컬 참고): Kuhn k=2 0.170→0.056, Leduc 1×1 2.36→0.98.
## 경보
- **#312 metrics 스냅샷 타임아웃**(P0). 원인 후보: metrics.py가 pytest 전체를 직렬 재실행.
- **main CI 완료 간격**: 머지 간격 < CI 시간으로 main run 대부분 cancelled(18:08~19:43 6건 연속). 하네스 후보(Auditor).
- **gh CLI 토큰 무효·GraphQL 403·guard 훅** → 전 역할 MCP 우회(오늘 friction 10회+). 후보: 지침의 gh 예시를 MCP 기준으로.
- 취소된 run이 같은 sha에 gates=failure를 남김(friction 7회+: 라벨 편집 직후 첫 run 취소). 후보 유지.
- 머지로 닫힌 이슈의 in-progress 라벨 잔존(planner 수동 정리 반복, 닫힌 이슈 89건 누적). 후보: reviewer가 머지 시 제거.
- builder/builder-b/세션 PR 소유 구분 불가(friction 3회+). gates quick 417~465초(목표 90초), full 백그라운드 실행 중 워커 재시작으로 결과 유실(friction 3회).
- RunPod 측정 이슈는 명세/실행이 한 PR로 안 끝남 → 앞으로 이슈를 둘로 나눈다(planner 반영).
- 이전 후보 유지: ARCHITECTURE.md 단일 줄 충돌, CHANGES 2회 규칙 예외, 동시 webhook 잠금, 머지된 브랜치 삭제 도구 없음(#105).
- NEEDS_HUMAN: NH-3 open. 리포 상호작용 제한 2027-04-23 만료.
## 진행 중 실험 (Auditor 소유, 그대로 유지)
- 001 builder 자가 언블록 (#55 머지 PR #57, 10-25 03:50Z). 측정창: 머지 후 14일. 성공 기준: builder no_work ≤10%(기준 24%), 처리량 80% 이상 유지.
- 009 planner run_on_merge (#130 PR #131 머지 51686a6, 10-27 12:38Z). 기록: harness/experiments.
- 015 gates 시간 상한 50분 (#199 PR #200 머지 6508d38, 10-27 18:28Z). 기록: harness/experiments.
