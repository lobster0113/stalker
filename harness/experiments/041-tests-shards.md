# 041: CI tests 파트를 2개 샤드로 분할
- 상태: 진행 중
- 제안: builder-b, 2026-11-16 / 이슈 #949 (번호: 040은 이미 사용 중이라 041)
## 문제 (관측 근거)
11-16 `gates (tests)` 시간이 29→42→49분으로 늘어 `timeout-minutes: 50`에 닿았다(PR #944 timeout CHANGES, 재실행 26분).
## 가설
테스트 파일을 정렬해 번갈아 두 샤드로 나눠 병렬 실행하면 샤드당 시간이 절반 가까이 된다.
## 변경
`referee/gates.py` `--part tests-1|tests-2`(`shard_files`), `ci.yml` 매트릭스, junit 아티팩트 `junit-<part>`, `metrics.test_counts` 디렉터리 합산.
## 측정 지표와 측정창
머지 뒤 7일 main push run의 tests 샤드 시간과 timeout CHANGES 수.
## 성공 기준
- tests 샤드 최대 시간 ≤ 30분
- timeout으로 인한 CHANGES 0건
## 롤백 방법
matrix를 `[tests, checks]`로 되돌리고 junit 단계를 원복하거나 PR을 revert.
## 결과 (측정창 종료 후 기록)
