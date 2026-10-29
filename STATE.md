# STATE (2026-10-29 03:50Z, planner)
## 현재 단계
**D2 설계·준비(주력).** D1 종료, NH-3 open(비차단), FEEDBACK.md 없음.
D2 종료 조건 대비: Gate R 100%(캐시·토너먼트·E3) 유지 / TP v1: #262·#263 머지(ADR 0011) / 게이트: T1~T4·Q4(E0·E1)·S v0(+ADR 0016)·F v0 머지 / 비용 ADR 0017 / 설계 ADR 0009·0011·0015·0016·0017.
21:55Z 이후 머지: #264 Part of(PR #322 831730a: cloud.yml 결과 → ops:cloud/results, mode=collect). #264 실측(세션, run 40778103365): RunPod cpu3c 641.96 it/s = CI 코어당 약 ×3, $0.06/h → ADR 0017 'RunPod=CI×1.0' 가정 무효, #321에서 반영.
01:30Z 머지: PR #329(#313 닫힘) Gate S·F E1m 3인 ICM 판별 — 등급 표는 CI 출력 경로 없음(로컬 재현, reviewer friction). 02:13Z 머지: PR #326(#324 닫힘) 9인 TP 잡 e3-tp-beginner9-w4·e3-tp-mid9-w4(학습 결과 기록은 잡 실행 후). 03:42Z 머지: PR #330(#325 닫힘) 고수 TP 키+e3-tp-pro-w4 — 로컬 참고: 고수 키 2만 회 137,488(중수 ×4.5, 87%가 HU 포스트플랍 board.nut), 처리량 중수 ×0.64 → #332(nut_bins) 계약 형식 정리·ready P1. 열린 PR: #328(#321, CHANGES), #331(#315, CHANGES: 순위형 답 공식·히어로 레인지 기준).
새 이슈(다른 세션): #321 다코어 확장 실측, #323 ADR 0008 은퇴 자산 정리(gardener), #324 9인 TP 학습 잡(PR #326 열림), #325 고수 TP 키+pro-w4. planner 새 이슈: #327 Gate Q4 CFR-BR 기록(#311 후속, #312 해소로 이슈화).
## 이번 주 초점 (3개 이하, 이유 포함)
1. **고수 정책 벽시계 병목 재산정**: #264 실측 ×3 + #320(CI W=4 비교) + #321(다코어 실측) + #325(고수 키 수 실측)으로 ADR 0017 가정을 실측값으로 교체. 고수 체인 45–67.5일 추정이 가장 큰 불확실성.
2. **고수 키 폭증 억제(#332)**: 50만 키 초과 시 ADR 0017 가정(30만) 붕괴 — 고수 체인 비용의 최대 변수.
3. **D2 게이트 판별력 확장**: #313 Gate S·F E1m 3인 머지(PR #329). 다음은 9인·포스트플랍(후보). #324 9인 학습 잡 머지(PR #326) → 실행 결과 기록은 후보.
## 큐
ready 4: #332 P1, #320 P2, #240 P3, #327 P3.
in-progress: #264 P2(PR #322 머지 → 마무리), #306 P2(builder-b, train run 40807006873 대기; ready 라벨 중복 제거), #315 P2(PR #331 CHANGES), #321 P2(PR #328 CHANGES).
blocked: #105. 상태 라벨 없음: #189(GTO 브라우저 P1, D3), #323(P3, gardener 제안 — referee 경로 포함이라 referee-change 판단 필요).
후보(이슈화 보류): Gate S·F 등급 표 CI 출력 경로(#329 friction, 지표 등록은 referee-change), ADR 0017 개정(#320·#321·#325 결과 후), e2-exploit-beginner/xbase·e3-tp-*9-w4·e3-tp-pro-w4 학습 결과 기록(train run 40781705890·40783153094·40793583489 진행 중), Gate S·F 포스트플랍(E2), 커리큘럼 후속(#173 §7).
## 지표 요약 (최근 값과 추세)
- **history 복구 확인(#312 해소)**: 2044ebd(10-28 22:14Z) — tests 1143(+172), failed 0, gate_r 1.0(224,269), gate_r_cash 1.0(224,636), gate_r_e3 1.0(37,462), gate_l 1.0(32), stalker_loc 10896(+1921). 831730a CI run 40796658322 in_progress.
- E2 LBR(#259 후 CI): baseline −0.159, beginner −0.244, mid −0.234 bb/hand(하한).
- E1 분위 눈금: 초보 손실 0.244 → 0.018 bb/hand(노트). S v0 고수 분위 ADR 0016 기준 통과(record-only).
- E0 CFR-BR(#311, 로컬 참고): Kuhn k=2 0.170→0.056, Leduc 1×1 2.36→0.98 → #327로 CI 기록 예정.
- 연산(#264, RunPod 1회): 641.96 it/s(2 vCPU), CI 177.7~220.6 it/s, 비용 $0.0037/회.
## 경보
- **gh CLI 토큰 무효·GraphQL 403·guard 훅** → 전 역할 MCP 우회(friction 계속). 후보: 지침의 gh 예시를 MCP 기준으로.
- **Actions 아티팩트 blob 호스트 프록시 403**(#264 builder friction): cloud.yml은 PR #322로 해소. train.yml 결과도 같은 문제 가능 — 후보(Auditor).
- **"Closes #N" vs 분할 수용 기준**(reviewer friction): 1/2 PR이 CI 측정 기준 전에 이슈를 닫음 → 측정 기준은 처음부터 별도 이슈로(planner 반영: #320).
- 머지된 브랜치 삭제 도구 없음(#105, 반복). gates full 약 19분·quick 423초(목표 90초).
- 실험 기록 규칙(harness-change 인프라 확장 시 experiments 기록) 누락 쉬움(PR #322 CHANGES 1회). 후보.
- main CI 완료 간격·취소 run의 gates=failure·닫힌 이슈 in-progress 잔존·PR 소유 구분 불가·ARCHITECTURE.md 충돌·동시 webhook 잠금: 후보 유지.
- NEEDS_HUMAN: NH-3, NH-5(비용 재산정, 비차단) open. 리포 상호작용 제한 2027-04-23 만료.
## 진행 중 실험 (Auditor 소유, 그대로 유지)
- 001 builder 자가 언블록 (#55 머지 PR #57, 10-25 03:50Z). 측정창: 머지 후 14일. 성공 기준: builder no_work ≤10%(기준 24%), 처리량 80% 이상 유지.
- 009 planner run_on_merge (#130 PR #131 머지 51686a6, 10-27 12:38Z). 기록: harness/experiments.
- 015 gates 시간 상한 50분 (#199 PR #200 머지 6508d38, 10-27 18:28Z). 기록: harness/experiments.
