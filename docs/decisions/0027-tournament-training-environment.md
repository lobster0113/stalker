# ADR 0027: E 토너먼트 학습 환경: env_id·단계·key·warm start A/B·첫 측정 run

- 상태: 제안. 이 PR이 머지되면 채택한다(Builder 추천안으로 진행, `harness/PROTOCOL.md` §9).
- 이슈: #880 (#385 E0). 관련: ADR 0019 §3.1 E·§3.2·§4, ADR 0026(보상 = ICM + 버블 보정 λ), #878(E3 BB 앤티)·#879·#883(ICM 보상 옵션)·#886(MCCFR ante·stage, c1 `t<stage><ante>`)·#887(웹 미러 앤티)·#888(병렬 워커 전달).
- **이 PR에서 직접 돌린 수치는 없다.** 아래 수치는 출처(문서·ops 경로·run id)를 적었고, 출처가 없는 수치는 **가정**이라고 표시했다. 성능 판단의 근거는 CI 결과뿐이다(CLAUDE.md).

## 맥락
D(#384)가 끝나 E(#385)에 들어간다. #385는 builder 한 번에 끝나지 않는다. 구현 전에 아래 열린 질문을 정해야 한다.
- 소유자 질문(2026-10-30, #385 코멘트): 페이아웃 구조와 블라인드 증가 속도를 학습에 넣는가.
- 설계 리뷰 RFC-08(#385 코멘트): 토너먼트는 별도 env_id·보상·후회값을 쓴다. warm start는 cold start와의 A/B에서 이겨야 한다. "정확 ICM"의 적용 범위를 정한다(한 테이블, 모든 스택이 알려짐). 단위(bb/100, $EV, ROI)를 섞지 않는다.

지금까지 들어간 코드(main ec28924a):
- `stalker.e3.mccfr.E3MCCFR`: `payoff="icm"`(#883), `ante`·`stage`(#886). 체크포인트는 버전 10이다. 기본값이면 예전 비트와 같다.
- c1 key의 예약 칸 `t<stage><ante>`(#400·#886): stage는 `tp_key.STAGES = c, e, b, m, f`다.
- `stalker.e3.icm_payoff.tournament_payoff`: 정확 ICM이고, 한 테이블이 남은 토너먼트 전체일 때만 맞다(모듈 문서).
- 병렬 워커(`stalker/e3/parallel.py`)는 아직 `payoff`·`ante`·`stage`를 거부한다. 이 전달이 #888이다.
- `pod_train` CLI에는 `--payoff`·`--ante`·`--stage`가 없다(`stalker/tools/pod_train.py` 인자 목록).
- 학습 스택 표본 `game.sample_stacks`는 캐시용으로 20–250BB를 로그 균등하게 뽑는다(`STACK_RANGE_BB`). 토너먼트 버블의 짧은 스택 분포와 다르다.

## 결정 1. 토너먼트 `env_id`에 들어가는 필드

**결정: `EnvSpec` 필드는 바꾸지 않는다.** 토너먼트 env_id는 프리셋의 `from_tournament(cfg)`가 낸 값을 그대로 쓴다. 학습 단계·λ·스택 표본은 env_id에 넣지 않는다. 이 값들은 학습 run의 **`train_env` 기록**(체크포인트·결과 JSON)에 둔다.

환경 분리 최소 키(`docs/research/2026-11-icm-env-separation.md` 「함의」)를 현재 필드와 대조한 표:

| 분리 키 | `stalker/env/spec.py` `EnvSpec` | `stalker/records/schema.py` | 처리 |
|---|---|---|---|
| 페이아웃 구조(상금 인원·가중) | `payout_vector`, `payout_mode` | 기록마다 `env_id`(v2) | 이미 있음. 다른 프리셋은 다른 env_id |
| 블라인드 증가 속도 | `blind_schedule` (sb, bb, length), `time_model` | 〃 | 이미 있음. turbo·regular·deep은 다른 env_id |
| 앤티 종류 | `ante_mode`(none·classic·bb_ante·dead), `ante_schedule` | 〃 | 이미 있음 |
| 인원(필드·테이블) | `field_size`, `table_size`, `initial_stacks` | 〃 | 이미 있음 |
| 잔여 인원 | 없음(상태) | 의사결정 기록의 상태 | env가 아니라 상태다. key의 `n<players>`와 `t<stage>`가 읽는다 |
| 바운티(PKO) | 없음 | 없음 | 범위 밖. 지원할 때 새 `kind`나 필드를 추가한다(ICM과 반대 방향 힘, 같은 문서) |
| 재진입 | `reentry_rule`("none"만) | 없음 | v1 그대로 |
| 학습 단계(e·b·m·f) | 없음 | 없음 | **env_id 밖.** 토너먼트 하나가 모든 단계를 지나므로 단계는 상태다. 학습 run의 `train_env.stage`와 key의 `t<stage>`에 둔다 |
| 보상 보정 λ | 없음 | 없음 | **env_id 밖.** 같은 환경을 푸는 학습 설정이다. `train_env.lam`(체크포인트 v9·v10에 이미 있는 `lam`) |
| 학습 스택 표본 | 없음 | 없음 | **env_id 밖.** `train_env.stacks`(예: `bubble:skewed`) |

근거:
- env_id는 "어느 게임인가"다. 기록·판정이 이 값을 참조한다. 페이아웃·블라인드·앤티가 다르면 이미 다른 id가 된다. 그래서 CHARTER의 환경 분리는 지금 필드로 지켜진다.
- 단계를 env_id에 넣으면 토너먼트 한 판의 기록이 단계마다 다른 env_id로 쪼개진다. 그러면 시뮬 상금(ADR 0026 이중 기록)을 한 판 단위로 묶을 수 없다.
- 기록 스키마는 바뀌지 않으므로 `schema_version`도 그대로다. 학습 결과에 `train_env`(env_id, stage, level_index, lam, stacks)를 더하는 일은 후속 F2에서 한다. 이것은 기록 스키마가 아니라 pod 결과 필드다.

## 결정 2. 학습 단계 목록과 첫 학습 단계

단계 정의(K = 상금 인원, r = 생존자 수). key의 `t<stage>`도 같은 규칙으로 정한다.

| stage | 뜻 | 조건 | ICM |
|---|---|---|---|
| `e` | 초반 | r ≥ K + 2 | SNG는 정확, MTT 다중 테이블은 추정(`icm_equity_mc`, "추정 ICM" 표시) |
| `b` | 버블 | r = K + 1 (ADR 0026의 g = 1과 같은 경계) | 〃 |
| `m` | 상금권 안 | r ≤ K이고 파이널 테이블이 아님. SNG는 r ≤ K 전체 | 〃 |
| `f` | 파이널 테이블 | MTT(`field_size > table_size`)에서 r ≤ `table_size`이고 상금권 안 | 정확(한 테이블) |
| `c` | 캐시 | 토너먼트 아님 | 해당 없음 |

- SNG는 `e`·`b`·`m`만 쓴다. SNG는 처음부터 한 테이블이라 `f`가 `m`과 같기 때문이다.
- 정확 ICM의 범위(RFC-08): **한 테이블에 남은 토너먼트 전체가 있고 모든 스택이 알려진 경우**만이다. 즉 SNG 전체와 MTT의 `f`다. `tournament_payoff`가 이 범위를 코드로 강제한다(생존 > `MAX_EXACT_PLAYERS`이면 거부). MTT `e`·`b`는 추정 ICM이고 TP.md의 `plan.icm` 규칙대로 "추정"으로 표시한다.

학습 순서(앞 단계의 결과가 다음 단계의 설정을 정한다):
1. **SNG `b`(첫 단계)**: `9max_sng_503020`, r = 4, 앤티 없음.
2. SNG `m`(같은 프리셋, r = 2·3, g = 0이라 λ가 꺼짐).
3. SNG `b` 앤티 있음(같은 프리셋에 BB 앤티 레벨. #878·#887 경로).
4. SNG `e`(r = 5–9, 9인 deal이 필요하다. D의 c1 범위는 2–6인이라 7–9인 key 확인이 선행된다).
5. MTT `f`(`mtt180_bbante`·`mtt54`의 파이널 테이블, 정확 ICM).
6. MTT `e`·`b`(추정 ICM, 다중 테이블 상태, 마지막).

**첫 단계를 `9max_sng_503020` 버블(r = 4)로 고른 이유:**
- ICM 편향이 측정으로 확인된 곳이다. #845에서 유의 칸 6개는 모두 버블이었고, 그중 3칸이 503020 r = 4였다(`docs/research/2026-11-icm-bias-measurement.md`). 2인 상금 `6max_sng_topheavy`의 버블(r = 3)은 1000게임으로 유의하지 않았다(같은 문서). 이슈가 예로 든 "6max SNG 버블"보다 학습 효과를 판별하기 쉽다.
- λ 기준선이 같은 격자에 있다(`docs/research/2026-11-icm-lambda-baseline.md`, 503020·flat × r 2–4, 로컬 참고값). ADR 0026의 CI λ 선택 절차를 학습된 정책으로 다시 돌리면 바로 비교할 수 있다.
- 4인 deal은 D의 c1 2–6인 key와 엔진 경로(`n4`, 좌석별 스택·사이드팟)를 그대로 쓴다. 새 딜 모양이 없다.
- 한 테이블이라 정확 ICM이다. 상금이 비균등이라(50/30/20) 상금권 안 비교 칸(단계 2)도 정보가 있다. `9max_sng_flat`의 r 2·3은 diff가 정의상 0이다(λ 기준선 문서 「위험」).

## 결정 3. 페이아웃 구조와 블라인드 속도를 key에 넣는 방식

**결정: 첫 단계부터 단계 3까지는 c1 예약 칸 `t<stage><ante>`로 충분하다. 새 key 버킷을 넣지 않는다.** 근거:
- 학습 run 하나는 프리셋(= env_id) 하나와 레벨 하나에서 돈다. 그 run 안에서 `payout_vector`·`paid_places`는 상수다. key에 넣어도 칸이 갈라지지 않고 정보도 늘지 않는다. 다른 페이아웃은 다른 env_id이므로 후회값도 따로 쌓인다(ADR 0019 §3.2).
- 버블까지의 거리(r − K)는 `t<stage>`가 이미 담는다. b는 1, m은 0 이하, e는 2 이상이다. 남은 생존자 수는 `n<players>`가 담는다.
- 블라인드 속도는 한 핸드의 게임 트리에 없다. 현재 레벨의 블라인드·앤티는 deal이 정하고, 스택 깊이는 c1 `s` 필드(`EFF_EDGES_BB = 5, 10, 15, 25, 40, 60, 100`)가 BB 단위로 읽는다. 다음 레벨까지의 핸드 수(`next_blind_change`)가 결정에 주는 영향은 미래 게임의 가치다. 그 효과는 보상 쪽 보정(ADR 0026 λ, FGS 성격)이 맡는다. key는 맡지 않는다.

**바뀌는 조건과 방법:**
- 정책 하나가 여러 프리셋이나 레벨을 함께 학습할 때(예: 서비스가 프리셋마다 정책을 둘 수 없을 때)는 페이아웃·블라인드 요약이 key에 필요하다. TP.md §1.2에 있는 공개 사실(`payout_vector`·`paid_places`·`blind_level`·`next_blind_change`)로 만든 버킷(다음 페이점프까지 거리, 다음 레벨 뒤 M 비율, 다음 레벨까지 핸드 수)을 쓴다. 이것은 **새 key 버전**(c1 → c2, `KEY_VERSIONS`)이다. 후회값은 다시 학습한다(ADR 0019 §3.2 "key가 바뀌는 경우").
- TP.md §1.2에 없는 사실이 필요하면 TP.md(보호 문서)를 바꿔야 한다. 그 일은 **referee-change 후속으로 분리한다.** 지금 목록에 있는 사실에서 계산한 버킷은 TP 변경이 아니다.
- 판단 근거: 단계 1–3에서 같은 env의 서로 다른 레벨 정책을 비교해 행동 차이가 크면(후속 F5 결과) c2 이슈를 연다. 측정 전에는 넣지 않는다.

## 결정 4. warm start A/B 설계

이슈가 든 세 갈래는 두 팔로 줄어든다. "엔진·특징 공유"는 모든 팔에 공통이기 때문이다. 코드와 key 함수는 같고, 후회값은 0에서 시작한다. 이것이 cold다.

| 팔 | 시작 상태 | 구현 |
|---|---|---|
| A cold | 후회값·평균 전략 0 (엔진·특징·레인지 코드는 C·D와 공유) | 지금 코드 그대로 |
| B C 평균 정책 prior | 후회값 0. 평균 전략 합을 C·D 정책(같은 tier의 c1 mixn 정책)의 평균 전략으로 초기화한다. key는 `t c0`을 `t<stage><ante>`로 바꾼 같은 key다. 가중치 `w`회분(가정: w = 그 key의 C 방문 수와 1000 중 작은 값) | 후속 F6 |
| (기각) 후회값 복사 | C의 후회값을 토너먼트 key로 옮김 | CHARTER 환경 분리와 RFC-08이 금지한다. 보상(목적함수)이 다른 후회값을 섞는다 |

- **같은 연산**: 두 팔 모두 같은 잡 명령·`--max-iters`·워커 수·시드 집합(1, 2, 3)을 쓴다. prior를 읽고 쓰는 시간은 학습 시간에 넣는다.
- **보지 못한 ICM 스팟**: 학습은 후속 F2의 스택 표본(시드 = 학습 시드)으로 한다. 평가는 `icm_grid`의 `--layouts` 배치로 한다. 평가 시드는 10001부터라 학습 rng와 겹치지 않는다. 프로필 even·random·skewed × 배치 ≥ 3이고, 503020 r = 4를 쓴다. 보조로 `9max_sng_skip`(같은 상금, 다른 블라인드 규칙)의 r = 4를 학습 env 밖 스팟으로 함께 잰다.
- **지표**(단위는 상금 풀 비율. bb/100과 섞지 않는다):
  1. 주 지표: 학습 정책 한 좌석, 나머지 좌석은 고정 필드(`persona:tag`)일 때 그 좌석의 **시뮬 상금 기대값 − ICM 에퀴티**(칸 평균, 95% CI). ADR 0026의 이중 기록 기준과 같다.
  2. 보조: 정책 대칭 필드의 ADR 0026 지표 (i)·(ii)(λ 선택 절차의 입력).
  3. 보조: 같은 스팟의 c1 key 칩 LBR(bb). record-only이고 판정에는 쓰지 않는다. ICM 단위 LBR은 심판 변경이라 후속 F4다.
- **채택 규칙**: 주 지표에서 B − A의 95% CI 하한이 0보다 크면 B를 채택하고, 아니면 A(cold)를 채택한다. 동률이면 cold다. 단순하고 prior 코드가 남지 않기 때문이다. 단계마다 다시 재지 않는다. 첫 단계 결과를 단계 2–3에도 적용하고, 단계 4(7–9인)에서 한 번 다시 잰다.
- **판정 결과(#937, 2026-11-17)**: 첫 단계(503020 버블 r=4) 쌍 3개 모두 B−A CI가 0을 포함해 **cold A 채택**. 근거: [`docs/research/2026-11-e-f6-warm-start-ab.md`](../research/2026-11-e-f6-warm-start-ab.md).

## 결정 5. 첫 측정 run 명세 (디스패치·기록 2회 실행 전제)

목적: 첫 단계 env에서 cold 팔(A)이 끝까지 학습되고, key 분포가 정상(`t b0` 칸만 생기고 `n4`)이며, 칩 LBR이 기록되는지 확인한다. ADR 0019 §3.3의 "D·E 첫 파드 run"에 해당한다.

| 항목 | 값 | 근거 |
|---|---|---|
| 잡 | `jobs/e3-tp-mid-c1-sng-bubble-pod32.yaml`(후속 F5가 추가) | jobs/README 형식 |
| 명령(요지) | `pod_train --tier mid --players 4 --workers 16 --minutes 60 --max-iters 20000 --batch 500 --seed 1 --menu real --no-raise-cap --ranges average --avg-rule own --key-variant c1 --payoff icm --preset 9max_sng_503020 --stage b --level-index 0 --lam 0 --stacks bubble:skewed --lbr-hands 600` | `--payoff`·`--preset`·`--stage`·`--level-index`·`--lam`·`--stacks bubble:<프로필>`(F2, #899; 이 잡은 ICM 편향이 큰 `skewed`)은 F2가 만든다. `--lbr-hands`는 F5(#901)가 더했다. 나머지는 `jobs/e3-tp-mid-c1-mixn-s4-pod32.yaml`과 같다 |
| λ | 0(순수 ICM) | ADR 0026: λ는 학습된 정책으로 나중에 고른다. 첫 정책은 λ 기준선이 필요 없는 0으로 만든다 |
| 시드 | 학습 1, 평가 10001 | A/B는 시드 2·3을 더한다(결정 4) |
| 반복 수 | 20,000 | **가정.** mixn 2–6인 c1이 16워커·90분에 40k–56k에 닿았다(`jobs/e3-tp-mid-c1-mixn-s4-pod32.yaml` 주석, #542). 4인 고정이라 반복당 비용이 그보다 크지 않다고 보고 60분 상한으로 잡았다. `stopped_by`가 어느 상한이 끝냈는지 남긴다 |
| 평가 | 칩 LBR(n = 4, 600핸드, ADR 0020의 4인 핸드 수) + key 분포(`t`·`n` 칸별 수) | 시뮬 상금 평가는 F3 뒤의 A/B run에서 한다 |
| 파드 | cpu3c 32 vCPU, `hourly_usd: 1.2`, `max_minutes: 180` | 단가는 jobs/README·위 잡과 같다 |
| 비용 | 최악 1.2 × 180 / 60 = **$3.60** (≤ $5) | 11월 원장 약 $20.11 / $100(ops:STATE.md 11-15 01:30Z 지표 요약). 실행 후 약 $23.7 / $100 이하 |
| 실행 | 1회차: PR 머지 후 `cloud.yml mode=run`을 디스패치하고 run id를 이슈에 남긴다. 2회차: `ops:cloud/results/<run id>.json`을 읽어 연구 문서에 기록하고 다음 단계를 판단한다 | #503 반영, STATE friction (e) |

- 선행: #888(병렬 워커가 `payoff`·`ante`·`stage`를 받음)과 F2(CLI·스택 표본·`train_env` 기록).
- 실패 시: RunPod 429·용량 부족은 run을 다시 디스패치한다(#877 2회차 사례: 동시 디스패치 2잡이 429). 이 잡은 단독으로 디스패치한다.

## 결정 6. 후속 이슈 (의존 순서)

이미 있는 이슈와 겹치지 않게 적었다. E1 앤티(#878 완료, #887 웹 미러)와 E2 보상(#879·#883 완료, #886 완료, #888 진행)은 다시 만들지 않는다.

| # | 영역 | 내용 | 선행 |
|---|---|---|---|
| F1 | ai | **#888**(이미 있음): 병렬 워커에 payoff·payouts·lam·ante·stage 전달 | 없음 |
| F2 | ai | `pod_train`·`train_jobs`의 `--payoff icm --preset --stage --level-index --lam --stacks bubble`, 토너먼트 스택 표본 `sample_tournament_stacks(rng, preset, remaining, level_index, profile)`(icm_calibration의 `make_start_state` 프로필 재사용, 칩을 E3 BB 단위로 환산), 결과·체크포인트에 `train_env`(env_id = `from_tournament(preset)`, stage, level_index, lam, stacks) 기록. 기본값이면 비트가 같다는 테스트 | F1 |
| F3 | ai | E3 정책을 토너먼트 에이전트로 감싸기(`stalker/tournament/director.py`의 좌석에 앉힘, 정책 미스는 규칙 봇 백오프와 표시) + A/B 평가 도구 `tournament_ab`(결정 4 지표 1·2, JSON) | F2 |
| F5 | ai | 첫 측정 run 잡 `jobs/e3-tp-mid-c1-sng-bubble-pod32.yaml`(결정 5). 1회차 디스패치, 2회차 기록 | F2 |
| F6 | ai | warm start prior 팔(`--prior-result`: C·D 평균 정책으로 평균 전략 합 초기화, key `tc0 → t<stage><ante>`) + A/B 잡 2개(A·B, 시드 1–3)와 판정 기록 | F3, F5 |
| F7 | ai | λ CI 선택을 학습 정책으로 실행(ADR 0026 절차, `icm_grid --agents policy:<run>`) | F3, F5 |
| F4 | referee (referee-change) | 토너먼트 평가의 "보정 에퀴티 + 시뮬 상금" 이중 기록과 ICM 단위 LBR을 심판에 연결(ADR 0026 후속 3, #385 기준 4 "LBR and field in CI") | F3 |
| F8 | service | 웹 토너먼트 모드가 학습 정책이 있는 단계(env_id·stage)에서는 그 정책을 쓰고, 나머지는 "미학습(규칙 봇)"으로 표시(#385 기준 5, ADR 0019 §7) | F5(정책 export), #887 |
| F9 | ai / (조건부 referee-change) | 결정 3의 c2 key(페이아웃·블라인드 요약 버킷). F5·단계 2 결과가 필요를 보일 때만 연다. TP.md §1.2 밖의 사실이 필요하면 referee-change | F5 |
| F10 | ai | 단계 4 준비: 7–9인 c1 key·`C1_POSITIONS` 확인과 측정(ADR 0019 9인 경로) | F6 |

## 결과
- 이 ADR은 코드, 심판 경로, TP.md, 예산 상한을 바꾸지 않는다.
- ADR 0019 §3.1의 E 행에 이 ADR 링크를 더한다.
- 위험:
  - 20k 반복과 60분은 가정이다. 첫 run의 `stopped_by`와 it/s로 바로잡는다.
  - 단계별로 정책을 따로 두면 서비스가 정책 파일을 단계 수만큼 갖는다(F8). 웹 정책 바이트 상한은 ADR 0021·#775 경로로 본다.
  - prior 팔의 가중치 `w`는 가정이고 A/B 한 번으로만 검증한다.
  - 평가 필드가 `persona:tag` 하나라 필드 의존성이 남는다. F3에서 필드를 2종(tag·random)으로 넓힐 수 있다.

## 재검토 조건
- 첫 측정 run에서 key가 예상 칸(`tb0`·`n4`) 밖으로 퍼지거나 LBR이 비정상이면 결정 3(key)을 다시 연다.
- A/B 결과가 단계 4에서 뒤집히면 결정 4의 채택을 단계별로 바꾼다.
- 바운티나 재진입을 지원하게 되면 결정 1의 EnvSpec 필드를 다시 연다.

- 판정 전환(F4, 지표·임계값·min_seeds): [ADR 0030](0030-tournament-eval-thresholds.md).
