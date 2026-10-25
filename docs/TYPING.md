# 유형화 v0 (스팟 키 · 셀 통계 · 충분성 리포트)

M1 프로토타입의 2) 과정 첫 결과물. 참조 봇(Gate B 참조 봇 v1) 토너먼트 기록으로 파이프라인을 검증한다. 실제 학습 대상 AI는 M2의 RL 정책이다.

## 실행
```bash
python -m stalker.pipeline.generate --preset sng9 --n 200 --seed 1 --out runs/sng9-s1
```
`--preset`은 별칭(`sng9`=`9max_sng_flat`, `sng6`, `sng6wta`, `sng9tt`, `mtt54`, `mtt180`), 프리셋 이름, 설정 JSON 경로 중 하나. 출력 디렉터리: `manifest.json`·`records.jsonl`(기록 스키마 v1, 쓰는 즉시 검증) + `report.json`·`report.md`. 게임당 약 5초(9인 SNG, 참조 봇 몬테카를로 포함). 같은 `--seed`·코드면 같은 기록이 나온다. 핸드 기록(`HandRecord`)은 아직 만들지 않는다.

## 스팟 키 (`stalker/typing/spots.py`)
| 축 | 값 |
|---|---|
| 단계 | `early`(남은 인원 ≥ 필드의 70%) · `mid` · `bubble`(상금권+1) · `itm`(상금권 이내) · `final`(다중 테이블 대회에서 남은 인원 ≤ 테이블 크기) |
| 유효 스택(BB) | `<5`·`5-10`·`10-15`·`15-25`·`25-40`·`40+` (내 칩과 핸드 중인 상대 최대 칩의 작은 쪽) |
| 포지션 | BTN SB BB UTG MP HJ CO (헤즈업은 BTN=SB, BB) |
| 스트리트 | preflop flop turn river |
| 팟 유형 | `unopened` · `facing_open` · `facing_3bet+`(프리플랍), `facing_bet`(포스트플랍), `facing_allin`(콜이 내 스택 전부) |
| 상대 프로파일 | 기억 요약의 상대 평균 VPIP: `tight`(<25%) · `normal` · `loose`(>40%) · `unknown`(관찰 10핸드 미만) |

키를 못 만드는 결정(포지션 불명 등)은 `None`이며 리포트의 `unclassified` 비율로 드러난다. 한계: BB가 림프를 받았을 때는 `unopened`로 센다. 세분화 규칙(최소 잎 크기로 자동 분할)은 후속 작업.

## 리포트 (`stalker/typing/report.py`, `schema_version` 3)
셀마다 결정 수·게임 수, 액션 범주(`fold`/`call`/`raise`/`allin`)별 평균 확률(= AI 혼합전략 빈도), 그리고 **심판 계산기 `referee.sufficiency.judge_cell`의 판정**: `s1`(정밀도)·`s4`(재현성)·`s5`(포화)·`lessonable`(= S1∧S4∧S5, 헌장 5: 이것만 가르친다). 리포트는 자체 충분성 계산을 하지 않는다.

**S4용 두 시드 집합 나누기**: 셀의 게임을 입력(결정 스트림)에서 처음 나온 순서로 번호 매겨 짝수 번째 → A, 홀수 번째 → B로 나눈다. `generate`는 게임 i를 시드 `[seed, i]`로 돌리고 게임 순서대로 기록하므로 A·B는 서로 겹치지 않는 시드 집합에서 나온다. 판정은 양쪽으로 한다: `judge_cell(A, B)`와 `judge_cell(B, A)`. `s1`·`s5`는 두 쪽 모두 통과해야 참, `s4`는 A↔B 일치. 셀에는 `n_games_ab`(A/B 게임 수)를 함께 적는다. 한쪽이라도 게임이 2개 미만이면 `status: insufficient_games`(S1 불가)다. 행동별 `half_width`·`ess`는 주요 액션(평균 ≥ 5%)에 대해 두 쪽 중 나쁜 값이다. 분산 0이면 `ess`는 그 쪽 게임 수(rule-of-three의 n)다.

요약: `cells`, `lessonable_cells`, `d1_preliminary.lessonable_decision_share`(교훈 가능 셀이 차지하는 결정 비율). 이 D1은 **예비값**이다. 이 데이터(참조 봇)의 결정 빈도로 가중했을 뿐 실전 출현 빈도가 아니므로 D1 판정이 아니다.

**분산 0 행동**: 심판의 S1은 반폭을 max(부트스트랩 반폭, 3/쪽 게임 수)로 잡는다(rule-of-three, `referee/DATA_SUFFICIENCY.md` S1). 그래서 결정론적인 작은 셀(쪽마다 게임 2개)은 S1에서 떨어지고, 쪽마다 게임 ≥ `ceil(3 / S1_HALF_WIDTH)` = 60이어야 통과한다. 리포트 v2의 임시 가드(`zero_variance_guard`)는 v3에서 없어졌다.

학습 페이지 빌더(`stalker/service/build.py`)는 v1 리포트도 읽는다(`upgrade_report`). v1은 S4/S5를 판정하지 않았으므로 모든 셀이 `lessonable: false`가 된다. v2는 S1에 rule-of-three 상한이 없었으므로, 쪽마다 게임이 60 미만인 셀의 `s1`·`lessonable`을 false로 내리고 반폭·ESS를 상한에 맞춘다. 퀴즈는 `lessonable` 셀에서만 뽑고, 페이지는 나머지 셀을 "표본 부족"으로 표시한다.

## 리포트를 `ops` 브랜치에 올리기
```bash
git fetch origin ops && git worktree add ../ops origin/ops -B ops   # 이미 있으면 git -C ../ops pull --rebase origin ops
mkdir -p ../ops/reports/typing/<run_id>
cp runs/<run_id>/report.json runs/<run_id>/report.md runs/<run_id>/manifest.json ../ops/reports/typing/<run_id>/
git -C ../ops add -A && git -C ../ops commit -m "<role>: typing report <run_id>" && git -C ../ops push origin ops
```
`records.jsonl`은 크므로 올리지 않는다. `manifest.json`(설정·시드·git sha)은 같이 올려 재현 가능하게 한다.
