# ICM 버블 보정 λ 기준선: ICM 모르는 에이전트 (#870, ADR 0026 후속 2b)

> **로컬 참고값, CI 결과 아님, λ 채택 아님** (ADR 0026: 채택은 #385의 학습된 토너먼트 정책으로 CI 선택 절차를 돌려 정한다). 한 머신(4코어)에서 2026-11-14에 아래 명령으로 만든 값이다. 원본: `docs/research/data/icm-lambda-2026-11-14-{random,tag}.json`(schema_version 3, 같은 이름 `.md`는 도구가 낸 칸별 표).

## 질문
1. `icm_grid --lambda-grid`(#866)가 실제 크기 격자(54칸 × 1000게임)에서 끝까지 도는가?
2. ICM을 모르는 에이전트(random·persona:tag) 기준으로 ADR 0026 4단계 규칙은 어떤 λ를 고르고, λ=0(순수 ICM)에 비해 무엇이 달라지는가? #385 정책과 비교할 출발점.

## 방법
- 격자: 프리셋 `9max_sng_503020`·`9max_sng_flat`(둘 다 상금 3명) × remaining {2, 3, 4} × 프로필 {even, random, skewed} × 레벨 0 × 배치 3 = 54칸, 칸당 1000게임, 시드 0. λ 격자는 기본값 0, 0.05, 0.1, 0.2, 0.35, 0.5.
- 구역: remaining 4 = 버블(18칸), remaining 2·3 = 상금권 안(36칸).
- 재현 명령(그대로):
```bash
python -m stalker.tools.icm_grid --presets 9max_sng_503020,9max_sng_flat --remaining 2,3,4 \
    --profiles even,random,skewed --level-index 0 --layouts 3 --games 1000 --seed 0 \
    --agents random --lambda-grid \
    --out docs/research/data/icm-lambda-2026-11-14-random.json --md docs/research/data/icm-lambda-2026-11-14-random.md
python -m stalker.tools.icm_grid --presets 9max_sng_503020,9max_sng_flat --remaining 2,3,4 \
    --profiles even,random,skewed --level-index 0 --layouts 3 --games 1000 --seed 0 \
    --agents persona:tag --lambda-grid \
    --out docs/research/data/icm-lambda-2026-11-14-tag.json --md docs/research/data/icm-lambda-2026-11-14-tag.md
```
  걸린 시간(참고, 두 명령 동시 실행): random 13분 50초, persona:tag 31분 0초. 45분 안이라 `--games 1000` 그대로.
- 유의 기준·지표는 ADR 0026 3단계와 같다: 칸이 유의 = 생존자 최대 |z| ≥ 3 **그리고** 최대 |sim − 보정 에퀴티|/pool ≥ 0.02. (i) 버블 유의 칸 수, (ii) 버블 칸 `max|diff|/pool` 평균, (iii) 상금권 안 유의 칸 수.

## 결과: λ 요약 (JSON `lambda_summary`)
| agents | selected λ | (i) 버블 유의 λ=0 → 선택 λ | (ii) 버블 평균 \|diff\|/pool λ=0 → 선택 λ | (iii) 상금권 안 유의 λ=0 → 선택 λ |
|---|---:|---:|---:|---:|
| random | 0.1 | 9 → 6 (/18) | 0.0240 → 0.0157 | 0 → 0 (/36) |
| persona:tag | 0.2 | 6 → 3 (/18) | 0.0248 → 0.0128 | 0 → 0 (/36) |

λ 전체:

| λ | random (i) | random (ii) | tag (i) | tag (ii) |
|---:|---:|---:|---:|---:|
| 0 | 9 | 0.0240 | 6 | 0.0248 |
| 0.05 | 6 | 0.0181 | 5 | 0.0168 |
| 0.1 | **6** | **0.0157** | 3 | 0.0130 |
| 0.2 | 7 | 0.0183 | **3** | **0.0128** |
| 0.35 | 12 | 0.0278 | 5 | 0.0196 |
| 0.5 | 12 | 0.0353 | 8 | 0.0259 |

(iii)은 모든 λ에서 두 에이전트 모두 0이라 표에서 뺐다(후보 제외 없음).

## 해석
- **도구는 실제 크기에서 끝까지 돈다**(질문 1). 54칸, 건너뛴 칸 없음(`skipped` 빈 목록).
- **두 에이전트 모두 λ>0을 고른다**: 버블 유의 칸과 평균 오차가 λ 0.1~0.2에서 바닥을 찍고 0.35 이상에서 λ=0보다 나빠진다(과보정). ADR 0026의 "ICM은 버블 최단 스택을 과소평가한다"와 같은 방향이고, 보정 크기가 tag(0.2) > random(0.1)인 것도 #845의 "같은 칸에서 tag 편향이 더 크다"와 맞다 — 고정 보정값을 쓰지 않고 정책마다 다시 고르는 ADR 0026 설계가 필요하다는 근거가 하나 더 생겼다.
- **선택 λ에서도 남는 유의 칸**(random 6, tag 3)은 대부분 skewed·random 프로필의 배치 의존이다. random에서는 λ=0.1이 503020 random 배치 1을 새로 유의로 만든다(0.0180 → 0.0256): 한 λ가 칸마다 맞지는 않는다. even 프로필(스택 같음)은 모든 λ에서 값이 같다(보정 항이 0).
- 상금권 안: 유의 칸 0. `9max_sng_flat`은 상금이 균등이라 remaining 2·3에서 모든 생존자 에퀴티가 같고 diff가 정확히 0이다(정보 없는 칸 18개). 503020 remaining 3 skewed는 |z|가 10을 넘지만 |diff|/pool이 0.02 미만이라 유의가 아니다(작지만 확실한 편향).

## 위험
- 에이전트가 ICM을 모르는 정책이라, #385 정책에서는 λ=0이 나올 수 있다(ADR 0026 「위험」). 이 문서는 비교 기준선이지 채택 근거가 아니다.
- 레벨 0만, 칸당 배치 3개, 다중 비교 보정 없음. 선택 규칙의 1차 키가 정수 칸 수라 칸 하나의 판정 변화에 민감하다(random에서 0.05와 0.1은 (i) 동률, (ii)로 갈림).
- `9max_sng_flat` remaining 2·3은 정의상 diff 0이라 (iii) 분모를 부풀린다. #385 측정에서는 상금권 안 칸을 503020 같은 비균등 상금으로 보는 편이 낫다(후속 후보).
