# 북극성 축별 CI 산출 현황 (2026-11-15, #892)

- 근거: `docs/CHARTER.md` 북극성 표, `referee/metrics.py`(`snapshot()`이 내는 키), `referee/GATES.md`, ops `metrics/history.jsonl` 최근 main 줄(63cf0a80 이후·e810934b 시점의 키 모양). **이 문서는 직접 돌린 수치가 없다.** CI 분·$ 추정은 출처가 적힌 곳 외에는 **가정**이다.
- 아래 "history 키" 열의 백틱 키는 `tests/test_north_star_coverage.py`가 `referee/metrics.py`가 내는 키 패턴과 대조한다(`<tier>` = beginner·mid·pro). 열에 "없음"만 적힌 행은 검사하지 않는다.

## 1. 축별 현황표

| 축(헌장) | (a) history 키 | (b) 없을 때 막는 것 | (c) 재산출 비용(가정) |
|---|---|---|---|
| 기반 — Gate R·L 통과율 | `gate_r_pass_rate`, `gate_r_cash_pass_rate`, `gate_r_e3_pass_rate`, `gate_l_pass_rate` | — | 이미 산출 |
| 기반 — 시뮬레이터 처리량(핸드/초) | `sim_hands_per_sec` | 있음(키) — #903에서 등록. `bench_engine.bench("fast")` 9인·시드 0·10초. **보고 전용**(러너 편차) — 판정에 안 씀 | CI 10초 안팎, $0 |
| TP 준수 — Gate T | `gate_t_pass_rate`, `gate_t_checks` | 있음(키) — #902에서 등록. REGISTRY 전 정책 × T1~T4 | CI 1분 안팎, $0 |
| 둔감성 — Gate S | `gate_s_e1` | E1(헤즈업 푸시/폴드)만. E1m·E3는 기록 전용 CLI | 이미 산출(E1) |
| 강도 Q1 — 상대군 대비 | 없음 | E3 필드 결과는 ops `training/` 요약에만 있고 history에 안 옮긴다 | 클라우드 run 결과를 복사만 하면 CI $0 (`e3_web_lbr` 선례) |
| 강도 Q2 — 앵커·솔버 손실 | 없음 | 앵커 비교는 Gate S·F 안에서만 쓰이고 독립 키가 없다. 솔버 스팟은 TexasSolver 워크플로 수동 | 앵커: 추가 계산 거의 없음. 솔버: 별도 워크플로 |
| 강도 Q3 — 발견된 착취 이득(LBR) | `e3_web_lbr` | 서비스 정책 한정. `fresh: false` 줄은 추세에서 제외 | 이미 산출(복사) |
| 강도 Q4 — 균형 인증 | `e0_kuhn_cfr_exploitability`, `e0_leduc_cfr_exploitability`, `e1_tp_<tier>_exploitability`, `e1_nash_fp_exploitability` | E1·장난감 게임만(인증 가능한 환경) | 이미 산출 |
| 복잡성 비용 | 없음 | 병목 없는 기준 정책의 Q 지표가 없어서 차이를 못 낸다 | Q1~Q3 전제. 클라우드 |
| 3인 이상 상대 집합 대비 최대 손실 | 없음 | E3 필드 결과(ops `training/`)를 history에 안 옮김 | 복사만이면 $0 |
| 착취 계층 | 없음 | 착취 계층 구현 전(ADR 0015 2층) | 구현 후 클라우드 |
| 따라 하기 — Gate F | `gate_f_e1_<tier>_nash_loss`, `gate_f_e1_<tier>_nash_loss_added` | E1만. E1m은 보고 CLI | 이미 산출(E1) |
| 서비스 — Gate U | 없음 | E2E·접근성·성능은 CI 잡 통과/실패와 아티팩트뿐 | 이미 도는 잡의 요약 JSON 한 줄. 추가 분 0 |
| 학습 — Gate E | 없음 | 시뮬레이션 학습자 평가기 부재(D4) | 평가기 구현 전 |
| 하네스 | 없음 (`tests_passed`, `tests_failed`, `stalker_loc`만 코드 쪽) | 머지 처리량·리드타임은 GitHub에서 Auditor가 계산. history 소관 아님 | $0, Auditor 리포트 |

참고로 `tests_passed`·`tests_failed`·`stalker_loc`도 history에 있으나 북극성 축이 아니다(건강 보조).

## 2. "Gate A/B/C"라는 이름

ADR 0008로 Gate A·B는 성공 정의에서 빠졌고 코드·CI 지표도 은퇴했다(`referee/metrics.py` 머리 주석, #101; 마지막 값만 history에 남음). 현행 게이트는 R·L(기반)·T·S·Q·F·U·E(·X)다. Gate C라는 현행 게이트는 없다. 따라서 Auditor 리포트의 "Gate A/B/C 미산출"은 **대응 축이 없는 이름**이고 "미산출 축 = 위 표의 '없음' 행"으로 읽어야 한다. 기울기(HARNESS_DESIGN §4.4)의 대상은 Gate Q 강도·Gate S 둔감성·Gate F 따라 하기이며, 지금 산출되는 것은 Q3·Q4(`e3_web_lbr`·`e0_*`·`e1_*`), S(`gate_s_e1`), F(`gate_f_e1_*`)다.

## 3. 가장 싼 재산출 후보

- **Gate T 통과율**(`gate_t_pass_rate`): 평가기와 스팟 세트가 이미 있고 `gates full`이 매번 돌린다. 등록만 하면 된다. → #902에서 등록 완료.
- **시뮬레이터 처리량**(`sim_hands_per_sec`): 헌장 "기반"의 두 번째 지표다. 러너 편차가 커서 판정이 아닌 추세용. → #903에서 보고 전용으로 등록 완료.

선택과 구현 경로는 ADR 0028.
