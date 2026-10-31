# 023: 지표 스냅샷이 테스트를 다시 돌리지 않게 — JUnit 넘겨받기
- 상태: 진행 중
- 제안: 대화 세션, 2026-10-29 / 이슈 #312
## 문제 (관측 근거)
main push CI의 `record-metrics`가 10-28 10:03Z(2deeb03) 이후 한 줄도 남기지 못했다. run 40756796767에서 gates(tests 12분·checks 14분)는 success였지만, `snapshot` 단계가 30분 타임아웃으로 cancelled됐다. `referee/metrics.py:test_counts()`가 같은 sha의 전체 pytest를 xdist 없이 직렬로 다시 돌린다. gates(tests)는 4 워커로 12분이 걸렸으므로 직렬이면 그것만으로 30분 한도를 넘긴다(#167: 직렬 테스트 21분, 그 뒤로 테스트가 늘었다).
## 가설
gates(tests) 잡이 남긴 JUnit 보고서로 테스트 수를 세면 중복 실행이 사라진다. 그러면 스냅샷 시간은 gate_r·gate_l·gate_s·E0·E1·Gate F를 합친 정도로 줄어 20분 안에 든다.
## 변경
- `.github/workflows/ci.yml`: tests 파트에 `PYTEST_ADDOPTS=--junitxml=junit.xml`을 주고 `junit` 아티팩트를 올린다. `record-metrics`는 그 아티팩트를 받아 `METRICS_JUNIT`으로 넘긴다. snapshot 단계에는 `timeout-minutes: 20`을 건다. PR에서도 스냅샷 입력 경로(`referee/metrics|gate_*|anchors`, `stalker/core|e1|e3|toy`, `ci.yml`)가 바뀌었으면 스냅샷까지만 돌린다(append 없음). 그래서 리뷰어가 PR CI에서 시간을 볼 수 있다.
- `referee/metrics.py`: `test_counts`는 JUnit 보고서가 있으면 그것을 세고, 없으면(로컬) `gates full`과 같은 워커 수로 돌린다. 단계별 초를 stderr에 `metrics: <단계> <초>s`로 찍는다.
## 측정 지표와 측정창
머지 후 main push 5회 또는 7일 중 먼저 오는 쪽. 근거는 CI 로그와 `ops:metrics/history.jsonl`뿐이다.
- `record-metrics` success 비율(다음 push로 취소된 run 제외).
- snapshot 단계 시간과 단계별 초(stderr).
- 각 성공 run의 sha 줄이 history에 생겼는지, 그 줄의 키 집합(기존 키 + gate_s_e1·e0·e1·gate_f_e1).
## 성공 기준 (수치)
- 취소되지 않은 run의 `record-metrics` success 100%.
- snapshot 단계 ≤ 20분.
- `tests_passed`가 같은 run의 gates(tests) pytest 요약의 passed 수와 같다.
## 롤백 방법
이 PR을 revert하면 이전 동작(직렬 재실행)으로 돌아간다. `METRICS_JUNIT`을 지우기만 해도 로컬과 같은 xdist 재실행으로 돌아간다.
## 결과
(측정창 종료 후 auditor가 기록)
