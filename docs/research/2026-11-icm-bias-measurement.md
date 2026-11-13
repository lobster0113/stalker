# ICM 편향 측정: 시뮬레이션 상금 vs ICM 에퀴티 (#845)

> **모든 수치는 로컬 참고값, CI 결과 아님.** 한 머신(4코어)에서 2026-11-13에 아래 명령으로 만든 값이다. 원본 JSON은 `docs/research/data/icm-bias-2026-11-13-{random,tag}.json`.

## 질문
1. 우리 시뮬레이터(`run_game`, 블라인드 증가·페이아웃 적용)에서 끝까지 돌린 실제 상금 기대값이 ICM(Harville) 에퀴티와 얼마나 다른가?
2. 그 차이가 표본 오차를 넘는 칸은 어디인가 — 프리셋·잔여 인원·스택 모양 중 무엇이 키우는가?
3. #385(토너먼트 학습)의 보상을 **순수 ICM 에퀴티**로 할까, **ICM+FGS식 보정**(리스크 프리미엄 하한 파라미터 하나, `2026-11-icm-env-separation.md`)으로 할까?

## 방법
- 도구: `stalker/tools/icm_grid.py`(#844, `--agents`는 #845). 칸마다 `make_start_state`로 같은 중간 상태(레벨 0, 블라인드 25/50)를 만들고 `icm_calibration.calibrate`로 1000게임을 끝까지 돌려 생존자별 `sim_prize_mean − icm_equity`를 잰다. 칸 시드는 칸 키로 정해진다(칸을 빼도 다른 칸 불변).
- 격자: 프리셋 3개(`6max_sng_topheavy` 65/35, `9max_sng_503020` 50/30/20, `9max_sng_flat` 1/3씩) × remaining {2,3,4} × 스택 프로필 {even, random, skewed} = 27칸, 에이전트 2종(`random` = `RandomLegalAgent`, `persona:tag` = 모든 좌석 TAG 페르소나).
- 재현 명령(그대로):
```bash
python -m stalker.tools.icm_grid --presets 6max_sng_topheavy,9max_sng_503020,9max_sng_flat --remaining 2,3,4 \
    --profiles even,random,skewed --games 1000 --seed 0 --agents random \
    --out docs/research/data/icm-bias-2026-11-13-random.json --md random.md
python -m stalker.tools.icm_grid --presets 6max_sng_topheavy,9max_sng_503020,9max_sng_flat --remaining 2,3,4 \
    --profiles even,random,skewed --games 1000 --seed 0 --agents persona:tag \
    --out docs/research/data/icm-bias-2026-11-13-tag.json --md tag.md
```
  걸린 시간(참고): random 508초, persona:tag 1114초(동시 실행).
- 열: `max|diff|/pool` = 칸의 생존자 중 최대 |sim − icm| ÷ 그 생존자들이 나눌 상금 합, `max|z|` = 최대 |diff| ÷ (sd/√games).

## 판정 규칙
칸마다: **|z| ≥ 3인 칸이 있고 그 칸의 |diff|/prize_pool ≥ 0.02이면 "편향 유의"**, 아니면 "표본 오차 범위". (표의 두 열이 모두 칸 최대값이라 같은 생존자가 아닐 수 있다 — 아래 유의 칸은 원본 JSON에서 같은 생존자로 다시 확인했다.)

## 결과

### 결과: random
| preset | remaining | profile | max\|diff\|/pool | max\|z\| |
|---|---:|---|---:|---:|
| 6max_sng_topheavy | 2 | even | 0.0033 | 0.70 |
| 6max_sng_topheavy | 2 | random | 0.0041 | 0.87 |
| 6max_sng_topheavy | 2 | skewed | 0.0037 | 0.79 |
| 6max_sng_topheavy | 3 | even | 0.0071 | 0.83 |
| 6max_sng_topheavy | 3 | random | 0.0196 | 2.29 |
| 6max_sng_topheavy | 3 | skewed | 0.0102 | 1.27 |
| 6max_sng_topheavy | 4 | even | 0.0181 | 2.13 |
| 6max_sng_topheavy | 4 | random | 0.0153 | 1.80 |
| 6max_sng_topheavy | 4 | skewed | 0.0204 | 2.42 |
| 9max_sng_503020 | 2 | even | 0.0020 | 0.51 |
| 9max_sng_503020 | 2 | random | 0.0015 | 0.37 |
| 9max_sng_503020 | 2 | skewed | 0.0068 | 2.15 |
| 9max_sng_503020 | 3 | even | 0.0032 | 0.83 |
| 9max_sng_503020 | 3 | random | 0.0099 | 2.41 |
| 9max_sng_503020 | 3 | skewed | 0.0105 | 10.69 |
| 9max_sng_503020 | 4 | even | 0.0096 | 1.64 |
| 9max_sng_503020 | 4 | random | 0.0046 | 0.92 |
| 9max_sng_503020 | 4 | skewed | 0.0435 | 11.73 |
| 9max_sng_flat | 2 | even | 0.0000 | 0.00 |
| 9max_sng_flat | 2 | random | 0.0000 | 0.00 |
| 9max_sng_flat | 2 | skewed | 0.0000 | 0.00 |
| 9max_sng_flat | 3 | even | 0.0000 | 0.00 |
| 9max_sng_flat | 3 | random | 0.0000 | 0.00 |
| 9max_sng_flat | 3 | skewed | 0.0000 | 0.00 |
| 9max_sng_flat | 4 | even | 0.0043 | 0.97 |
| 9max_sng_flat | 4 | random | 0.0209 | 4.79 |
| 9max_sng_flat | 4 | skewed | 0.0343 | 6.93 |

### 결과: persona:tag
| preset | remaining | profile | max\|diff\|/pool | max\|z\| |
|---|---:|---|---:|---:|
| 6max_sng_topheavy | 2 | even | 0.0030 | 0.63 |
| 6max_sng_topheavy | 2 | random | 0.0010 | 0.22 |
| 6max_sng_topheavy | 2 | skewed | 0.0047 | 1.01 |
| 6max_sng_topheavy | 3 | even | 0.0125 | 1.46 |
| 6max_sng_topheavy | 3 | random | 0.0147 | 1.71 |
| 6max_sng_topheavy | 3 | skewed | 0.0101 | 1.24 |
| 6max_sng_topheavy | 4 | even | 0.0099 | 1.15 |
| 6max_sng_topheavy | 4 | random | 0.0214 | 2.71 |
| 6max_sng_topheavy | 4 | skewed | 0.0164 | 1.90 |
| 9max_sng_503020 | 2 | even | 0.0035 | 0.89 |
| 9max_sng_503020 | 2 | random | 0.0010 | 0.25 |
| 9max_sng_503020 | 2 | skewed | 0.0005 | 0.16 |
| 9max_sng_503020 | 3 | even | 0.0079 | 1.98 |
| 9max_sng_503020 | 3 | random | 0.0040 | 1.06 |
| 9max_sng_503020 | 3 | skewed | 0.0026 | 4.46 |
| 9max_sng_503020 | 4 | even | 0.0082 | 1.47 |
| 9max_sng_503020 | 4 | random | 0.0168 | 3.22 |
| 9max_sng_503020 | 4 | skewed | 0.0603 | 15.53 |
| 9max_sng_flat | 2 | even | 0.0000 | 0.00 |
| 9max_sng_flat | 2 | random | 0.0000 | 0.00 |
| 9max_sng_flat | 2 | skewed | 0.0000 | 0.00 |
| 9max_sng_flat | 3 | even | 0.0000 | 0.00 |
| 9max_sng_flat | 3 | random | 0.0000 | 0.00 |
| 9max_sng_flat | 3 | skewed | 0.0000 | 0.00 |
| 9max_sng_flat | 4 | even | 0.0083 | 1.77 |
| 9max_sng_flat | 4 | random | 0.0400 | 7.61 |
| 9max_sng_flat | 4 | skewed | 0.0730 | 13.93 |

### 편향 유의 칸 (같은 생존자 기준, 원본 JSON에서)
| agents | preset | remaining | profile | 스택 | ICM | sim − ICM | z |
|---|---|---:|---|---|---|---|---|
| random | 9max_sng_503020 | 4 | skewed | 128 / 2814 / 1085 / 9473 | 26.1 / 278.6 / 203.4 / 392.0 | **+39.2** / −19.5 / −18.0 / −1.7 | 11.7 |
| random | 9max_sng_flat | 4 | random | 1297 / 3790 / 4717 / 3696 | 123.9 / 254.7 / 268.6 / 252.8 | +9.9 / +0.3 / +8.6 / **−18.8** | −4.8 |
| random | 9max_sng_flat | 4 | skewed | 2115 / 3420 / 457 / 7508 | 256.8 / 279.9 / 67.5 / 295.8 | −23.4 / −8.1 / **+30.9** / +0.6 | 6.9 |
| tag | 9max_sng_503020 | 4 | skewed | 128 / 2814 / 1085 / 9473 | 26.1 / 278.6 / 203.4 / 392.0 | **+54.3** / −25.9 / −24.3 / −4.2 | 15.5 |
| tag | 9max_sng_flat | 4 | random | 1297 / 3790 / 4717 / 3696 | 123.9 / 254.7 / 268.6 / 252.8 | **+36.0** / −13.2 / −0.4 / −22.4 | 7.6 |
| tag | 9max_sng_flat | 4 | skewed | 2115 / 3420 / 457 / 7508 | 256.8 / 279.9 / 67.5 / 295.8 | −41.4 / −20.7 / **+65.7** / −3.6 | 13.9 |

## 해석
- **유의 칸은 전부 버블(잔여 = 상금권 + 1)이다.** 3인 상금 프리셋의 remaining 4에서만 나오고, 상금권 안(remaining ≤ 상금 인원)은 표본 오차 범위다. `9max_sng_flat`의 remaining 2·3은 남은 상금이 모두 같아 차이가 정의상 0이다(판정에서 제외).
- **방향: ICM은 버블의 최단 스택을 과소평가한다.** 6칸 모두에서 가장 짧은 스택의 실제 상금이 ICM보다 크고, 그중 5칸은 그 차이가 칸 최대다(최대 +65.7 = pool의 7.3%). 상대들이 버블을 의식하지 않고 서로 부딪쳐 먼저 탈락하기 때문으로 보인다 — Harville 가정(순위 확률 ∝ 칩)은 남은 게임의 진행 방식을 모른다(FGS가 보정하려는 바로 그 지점).
- **편향 크기는 에이전트에 따라 다르다.** 같은 칸에서 tag가 random보다 크다(503020 skewed: +39.2 → +54.3, flat skewed: +30.9 → +65.7). 즉 편향은 ICM 모델만의 고정 오차가 아니라 **플레이 방식의 함수**다.
- 2인 상금 `6max_sng_topheavy`의 버블(remaining 3)은 random 0.0196/z 2.29, tag 0.0125/z 1.46로 기준 미달 — 2인 상금 구조에선 1000게임으로 유의하지 않다.

## 추천: ICM + 보정 (파라미터 하나, 기본 0)
- 판정 규칙상 **편향 유의**(6칸, 두 에이전트 모두). 순수 ICM 보상으로 학습하면 버블에서 짧은 스택의 가치를 체계적으로 낮게 보고, 그 오차가 pool의 2~7%다 — #385가 가장 공들일 버블 구간에서 틀린다.
- 다만 편향이 에이전트에 따라 바뀌므로 고정 보정표(우리 시뮬레이터 값)를 그대로 박으면 순환한다(학습된 정책이 바뀌면 편향도 바뀜). 그래서 **보상 = ICM 에퀴티 + 단일 파라미터 보정**(문헌의 리스크 프리미엄 하한, 기본 0이면 순수 ICM과 동일)으로 두고, 파라미터 값은 학습 정책끼리의 시뮬 상금으로 CI에서 고른다. 평가는 계속 "ICM 에퀴티 + 페이아웃 시뮬 상금" 이중 기록(`2026-11-icm-env-separation.md` 추천 2).
- 후속: 보정 형태와 CI 선택 절차를 정하는 ADR 이슈(PR 본문 "후속").

## 위험
- 측정 에이전트(`RandomLegalAgent`, TAG 페르소나)는 ICM을 모른다. ICM을 아는 정책끼리는 편향이 작아질 수 있다 — 추천을 "기본 0, CI로 고름"으로 둔 이유.
- 칸당 스택 배치 1개(시드 0). 프로필 이름이 같아도 배치가 바뀌면 값이 바뀐다. 시작 레벨 0(블라인드 25/50)만 쟀다 — 블라인드가 높으면 짧은 스택의 생존 이득이 줄 것이다.
- 1000게임에서 z 기준은 칸 27×2개에 대한 다중 비교 보정 없음. |z| ≥ 3 + 2% 크기 조건이 그 완충이다.
- 수치는 로컬 참고값이며 CI 결과가 아니다.
