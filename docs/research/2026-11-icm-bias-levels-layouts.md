# ICM 편향 재측정: 블라인드 레벨·스택 배치 (#858, #845 후속 B)

> **모든 수치는 로컬 참고값, CI 결과 아님.** 한 머신(4코어)에서 2026-11-14에 아래 명령으로 만든 값이다. 원본 JSON은 `docs/research/data/icm-bias-levels-2026-11-14-{random,tag}.json`(schema_version 2).

## 질문
1. #845의 버블 칸(remaining 4, 3인 상금) 편향은 시작 블라인드 레벨이 높아져도 남는가? (레벨이 높으면 푸시/폴드가 늘어 ICM에 가까워질 수 있다.)
2. 칸당 스택 배치 하나(#845의 위험 항목)가 결과를 좌우했는가 — 배치마다 판정과 방향이 같은가?

## 방법
- 도구: `stalker/tools/icm_grid.py`에 `--level-index`(쉼표 목록)·`--layouts N`을 추가했다. 레벨 0·배치 0은 이전과 같은 시드라 #845 숫자가 그대로 재현된다(테스트로 고정). 배치 k의 시드는 칸 키 + (레벨, k)라 레벨·배치를 빼도 나머지는 불변이다.
- 격자: 프리셋 `9max_sng_503020`·`9max_sng_flat` × remaining 4 × 프로필 {even, random, skewed} × 레벨 {0 (블라인드 25/50), 6 (300/600)} × 배치 3개 = 36칸, 칸당 1000게임, 시드 0, 에이전트 `random`·`persona:tag`.
- 재현 명령(그대로):
```bash
python -m stalker.tools.icm_grid --presets 9max_sng_503020,9max_sng_flat --remaining 4 \
    --profiles even,random,skewed --level-index 0,6 --layouts 3 --games 1000 --seed 0 --agents random \
    --out docs/research/data/icm-bias-levels-2026-11-14-random.json --md random.md
python -m stalker.tools.icm_grid --presets 9max_sng_503020,9max_sng_flat --remaining 4 \
    --profiles even,random,skewed --level-index 0,6 --layouts 3 --games 1000 --seed 0 --agents persona:tag \
    --out docs/research/data/icm-bias-levels-2026-11-14-tag.json --md tag.md
```
  걸린 시간(참고, 동시 실행): random 11분 18초, persona:tag 22분 29초.
- 열: `max|diff|/pool` = 칸의 생존자 중 최대 |sim − icm| ÷ 상금 합, `max|z|` = 최대 |diff| ÷ (sd/√games). 레벨 열은 시작 블라인드 레벨, 배치 열은 0~2.

## 판정 규칙
#845와 같다: 칸마다 **|z| ≥ 3인 칸이 있고 그 칸의 |diff|/prize_pool ≥ 0.02이면 "편향 유의"**. (두 열이 모두 칸 최대값이라 같은 생존자가 아닐 수 있다. 아래 요약은 원본 JSON에서 같은 생존자로 다시 계산했다.)

## 결과

### 결과: random
| preset | remaining | profile | level | layout | max\|diff\|/pool | max\|z\| |
|---|---:|---|---:|---:|---:|---:|
| 9max_sng_503020 | 4 | even | 0 | 0 | 0.0096 | 1.64 |
| 9max_sng_503020 | 4 | even | 0 | 1 | 0.0106 | 1.91 |
| 9max_sng_503020 | 4 | even | 0 | 2 | 0.0049 | 0.87 |
| 9max_sng_503020 | 4 | even | 6 | 0 | 0.0050 | 0.90 |
| 9max_sng_503020 | 4 | even | 6 | 1 | 0.0062 | 1.06 |
| 9max_sng_503020 | 4 | even | 6 | 2 | 0.0056 | 0.98 |
| 9max_sng_503020 | 4 | random | 0 | 0 | 0.0046 | 0.92 |
| 9max_sng_503020 | 4 | random | 0 | 1 | 0.0180 | 3.07 |
| 9max_sng_503020 | 4 | random | 0 | 2 | 0.0236 | 3.87 |
| 9max_sng_503020 | 4 | random | 6 | 0 | 0.0333 | 5.35 |
| 9max_sng_503020 | 4 | random | 6 | 1 | 0.0098 | 1.71 |
| 9max_sng_503020 | 4 | random | 6 | 2 | 0.0225 | 4.13 |
| 9max_sng_503020 | 4 | skewed | 0 | 0 | 0.0435 | 11.73 |
| 9max_sng_503020 | 4 | skewed | 0 | 1 | 0.0365 | 9.67 |
| 9max_sng_503020 | 4 | skewed | 0 | 2 | 0.0146 | 3.00 |
| 9max_sng_503020 | 4 | skewed | 6 | 0 | 0.0469 | 11.01 |
| 9max_sng_503020 | 4 | skewed | 6 | 1 | 0.0082 | 1.85 |
| 9max_sng_503020 | 4 | skewed | 6 | 2 | 0.0498 | 15.95 |
| 9max_sng_flat | 4 | even | 0 | 0 | 0.0043 | 0.97 |
| 9max_sng_flat | 4 | even | 0 | 1 | 0.0040 | 0.89 |
| 9max_sng_flat | 4 | even | 0 | 2 | 0.0017 | 0.37 |
| 9max_sng_flat | 4 | even | 6 | 0 | 0.0053 | 1.19 |
| 9max_sng_flat | 4 | even | 6 | 1 | 0.0047 | 1.04 |
| 9max_sng_flat | 4 | even | 6 | 2 | 0.0067 | 1.42 |
| 9max_sng_flat | 4 | random | 0 | 0 | 0.0209 | 4.79 |
| 9max_sng_flat | 4 | random | 0 | 1 | 0.0247 | 5.35 |
| 9max_sng_flat | 4 | random | 0 | 2 | 0.0268 | 5.09 |
| 9max_sng_flat | 4 | random | 6 | 0 | 0.0534 | 10.13 |
| 9max_sng_flat | 4 | random | 6 | 1 | 0.0494 | 9.37 |
| 9max_sng_flat | 4 | random | 6 | 2 | 0.0139 | 2.75 |
| 9max_sng_flat | 4 | skewed | 0 | 0 | 0.0343 | 6.93 |
| 9max_sng_flat | 4 | skewed | 0 | 1 | 0.0803 | 17.01 |
| 9max_sng_flat | 4 | skewed | 0 | 2 | 0.0699 | 16.20 |
| 9max_sng_flat | 4 | skewed | 6 | 0 | 0.0117 | 4.55 |
| 9max_sng_flat | 4 | skewed | 6 | 1 | 0.0381 | 7.78 |
| 9max_sng_flat | 4 | skewed | 6 | 2 | 0.0695 | 14.77 |

### 결과: persona:tag
| preset | remaining | profile | level | layout | max\|diff\|/pool | max\|z\| |
|---|---:|---|---:|---:|---:|---:|
| 9max_sng_503020 | 4 | even | 0 | 0 | 0.0082 | 1.47 |
| 9max_sng_503020 | 4 | even | 0 | 1 | 0.0052 | 0.92 |
| 9max_sng_503020 | 4 | even | 0 | 2 | 0.0050 | 0.90 |
| 9max_sng_503020 | 4 | even | 6 | 0 | 0.0085 | 1.47 |
| 9max_sng_503020 | 4 | even | 6 | 1 | 0.0065 | 1.13 |
| 9max_sng_503020 | 4 | even | 6 | 2 | 0.0082 | 1.41 |
| 9max_sng_503020 | 4 | random | 0 | 0 | 0.0168 | 3.22 |
| 9max_sng_503020 | 4 | random | 0 | 1 | 0.0150 | 2.65 |
| 9max_sng_503020 | 4 | random | 0 | 2 | 0.0102 | 1.81 |
| 9max_sng_503020 | 4 | random | 6 | 0 | 0.0087 | 1.53 |
| 9max_sng_503020 | 4 | random | 6 | 1 | 0.0122 | 2.21 |
| 9max_sng_503020 | 4 | random | 6 | 2 | 0.0113 | 1.95 |
| 9max_sng_503020 | 4 | skewed | 0 | 0 | 0.0603 | 15.53 |
| 9max_sng_503020 | 4 | skewed | 0 | 1 | 0.0511 | 13.46 |
| 9max_sng_503020 | 4 | skewed | 0 | 2 | 0.0186 | 3.56 |
| 9max_sng_503020 | 4 | skewed | 6 | 0 | 0.0133 | 3.64 |
| 9max_sng_503020 | 4 | skewed | 6 | 1 | 0.0180 | 3.95 |
| 9max_sng_503020 | 4 | skewed | 6 | 2 | 0.0166 | 8.90 |
| 9max_sng_flat | 4 | even | 0 | 0 | 0.0083 | 1.77 |
| 9max_sng_flat | 4 | even | 0 | 1 | 0.0050 | 1.07 |
| 9max_sng_flat | 4 | even | 0 | 2 | 0.0067 | 1.42 |
| 9max_sng_flat | 4 | even | 6 | 0 | 0.0100 | 2.29 |
| 9max_sng_flat | 4 | even | 6 | 1 | 0.0080 | 1.70 |
| 9max_sng_flat | 4 | even | 6 | 2 | 0.0073 | 1.56 |
| 9max_sng_flat | 4 | random | 0 | 0 | 0.0400 | 7.61 |
| 9max_sng_flat | 4 | random | 0 | 1 | 0.0020 | 0.46 |
| 9max_sng_flat | 4 | random | 0 | 2 | 0.0172 | 4.84 |
| 9max_sng_flat | 4 | random | 6 | 0 | 0.0072 | 2.14 |
| 9max_sng_flat | 4 | random | 6 | 1 | 0.0069 | 1.39 |
| 9max_sng_flat | 4 | random | 6 | 2 | 0.0251 | 4.77 |
| 9max_sng_flat | 4 | skewed | 0 | 0 | 0.0730 | 13.93 |
| 9max_sng_flat | 4 | skewed | 0 | 1 | 0.0763 | 16.39 |
| 9max_sng_flat | 4 | skewed | 0 | 2 | 0.0276 | 9.33 |
| 9max_sng_flat | 4 | skewed | 6 | 0 | 0.0166 | 5.66 |
| 9max_sng_flat | 4 | skewed | 6 | 1 | 0.0135 | 3.98 |
| 9max_sng_flat | 4 | skewed | 6 | 2 | 0.0242 | 4.66 |

## 요약 (JSON에서 계산, 칸 = 프로필 {random, skewed} 12개, even 12개는 어느 쪽도 유의 0)
| 에이전트 | 레벨 0 유의 칸 | 레벨 6 유의 칸 | 레벨 0 최단 스택 ICM 과소평가(sim>icm) | 레벨 6 최단 스택 과소평가 |
|---|---:|---:|---:|---:|
| random | 9/12 | 8/12 | 8/12 | 3/12 |
| persona:tag | 6/12 | 2/12 | 12/12 | 8/12 |

- even 프로필 칸은 두 레벨·두 에이전트 모두 유의 0/12(최대 |diff|/pool 0.011).
- 프리셋: random은 flat 레벨 0 6/9·레벨 6 4/9, 503020 레벨 0 3/9·레벨 6 4/9. tag는 flat 4/9→2/9, 503020 2/9→0/9.

## 해석
1. **레벨 효과는 에이전트에 따라 다르다.** persona:tag는 레벨 6에서 유의 칸이 6/12→2/12, 기울어진 칸(random·skewed 12개)의 평균 |diff|/pool이 0.034→0.0145, 최대는 0.076→0.025로 줄었다(기울어진 스택에서 편향이 줄어든다는 가설과 맞다). random 에이전트는 9/12→8/12로 거의 그대로이고 평균 |diff|/pool도 0.033→0.034다. 즉 "높은 레벨이면 편향이 사라진다"고 일반화할 수 없다.
2. **방향은 배치·에이전트마다 갈린다.** tag의 레벨 0에서는 최단 스택 12/12가 ICM보다 높게 나와(과소평가) 방향이 일관됐다. 레벨 6에서는 8/12, random은 8/12(레벨 0)→3/12(레벨 6)로 뒤집힌다. 방향이 바뀌는 칸은 #845 보정 파라미터(한 방향 하한)로 잡을 수 없다.
3. **배치 하나로는 부족했다.** 같은 칸 키에서 배치 0·1·2가 판정을 갈랐다(예: random 503020 skewed 레벨 0은 유의 2개·비유의 1개, flat random 레벨 6은 유의 2개·비유의 1개, tag flat random 레벨 0은 유의 1개(0.0400)·비유의 2개). #845 표의 개별 칸 유의 여부는 배치 의존이 크다.
4. 따라서 #845의 추천(ICM + 단일 파라미터 보정, 기본 0)은 뒤집히지 않지만, 보정 파라미터를 CI에서 고를 때(ADR 0026) **레벨·배치를 여러 개 섞은 평가 칸**이 필요하다는 근거가 늘었다. 이 문서는 ADR을 바꾸지 않는다.

## 위험
- 배치 3개·레벨 2개·remaining 4 한 개뿐이다. remaining 3·2인 상금, 6max 프리셋, 중간 레벨(1~5)은 측정하지 않았다.
- 1000게임에서 sd 기반 z는 칸당 생존자 4명 중 최대를 골라 다중 비교 편의가 있다(|z|≥3 판정이 다소 느슨).
- 에이전트는 `random`과 모든 좌석 TAG뿐이라 실제 플레이어 혼합과 다르다.
- 로컬 4코어 단일 실행이며 CI 값이 아니다.
