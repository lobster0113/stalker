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

## 리포트 (`stalker/typing/report.py`)
셀마다 결정 수·게임 수, 액션 범주(`fold`/`call`/`raise`/`allin`)별 평균 확률(= AI 혼합전략 빈도), 게임 단위 클러스터 부트스트랩 95% CI(`referee.stats.bootstrap_ci`, 1000회, 시드 고정), `ESS = p(1-p)/Var(p̂)`(근사: 퍼센타일 반폭에서 분산을 역산. 분산 0이면 `null` + `ess_note`), **S1** 통과 여부(평균 ≥ 5%인 모든 주요 액션의 반폭 ≤ 5%p). 게임이 2개 미만인 셀은 `insufficient_games`(데이터 부족)로 표시한다. 분산 0 셀(결정론적 등)은 부트스트랩 반폭이 0이라 정밀도의 증거가 못 된다. 그래서 반폭을 rule-of-three 상한 `3/게임 수`로 대체하고(95%에서 반폭 ≤ 5%p이려면 게임 ≥ 60), 모든 셀은 게임 ≥ 30(`MIN_GAMES`)이어야 S1을 통과한다. 통과한 결정론적 셀도 S4·S5(재현성·포화)는 아직 평가하지 않으므로 "교훈 가능"이 아니다. 정식 계산기는 #52(`referee.sufficiency`)이며 머지되면 후속 이슈에서 교체한다.

## 리포트를 `ops` 브랜치에 올리기
```bash
git fetch origin ops && git worktree add ../ops origin/ops -B ops   # 이미 있으면 git -C ../ops pull --rebase origin ops
mkdir -p ../ops/reports/typing/<run_id>
cp runs/<run_id>/report.json runs/<run_id>/report.md runs/<run_id>/manifest.json ../ops/reports/typing/<run_id>/
git -C ../ops add -A && git -C ../ops commit -m "<role>: typing report <run_id>" && git -C ../ops push origin ops
```
`records.jsonl`은 크므로 올리지 않는다. `manifest.json`(설정·시드·git sha)은 같이 올려 재현 가능하게 한다.
