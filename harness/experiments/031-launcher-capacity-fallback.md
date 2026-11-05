# 031: launcher flavor 대체·용량 지연 재시도·느린 호스트 1회 재발급
- 상태: 진행 중
- 제안: builder, 2026-11-01 / 이슈 #401 / PR #494 (ADR 0019 §6)
## 문제 (관측 근거: #373 연구 노트, ops:budget/ledger.jsonl)
결합 key 체인은 파드를 수십 번 돌려야 한다. #373에서 두 가지를 관측했다.
첫째, cpu3c 생성이 RunPod HTTP 500 "no longer any instances available"로 거절되면 run 전체가 실패했다. 비용은 $0이지만 디스패치를 한 번 날린다.
둘째, 같은 flavor라도 느린 호스트는 중앙값의 0.45배 속도였다. 같은 돈으로 반복을 절반만 얻는다.
#373 결과로는 cpu5c가 cpu3c보다 반복/$ 1.55배다.
## 가설
잡 명세에 flavor 목록(`[cpu5c, cpu3c]`)을 두고, 용량 거절이면 다음 flavor로 넘어간다. 목록이 다 막히면 15·30·60분 뒤에 다시 시도한다. 첫 진행 줄이 중앙값의 0.6배 미만이면 pod를 한 번만 다시 만든다. 이렇게 하면 용량 때문에 실패하는 run이 줄고, 최악 비용은 그대로다(flavor별 상한 ≤ `hourly_usd`).
끝내 pod를 만들지 못하면 ops 원장에 `create_failed`, `ops:journal`에 `role: cloud, outcome: failed` 줄(run id 포함)을 남긴다.
## 변경
- `harness/cloud/launcher.py`: `cpu_flavors`·`flavor_hourly_usd`·`median_iters_per_s` 명세 키, `CapacityError`/`CapacityExhausted`(종료 코드 3), `create_failed` 원장 줄, 결과 서버 `progress.json`, 느린 호스트 재발급, `--journal`.
- `.github/workflows/cloud.yml`: `--journal "$GITHUB_WORKSPACE/ops/journal"`. `harness/cloud/push_ledger.sh`: `journal/`도 커밋(union merge).
- c1 체인 잡 2개: `[cpu5c, cpu3c]`, 상한 `[1.2, 1.0]`.
## 측정 지표와 측정창
머지 후 c1 체인 잡(`e3-tp-mid-c1-pod32`, `e3-tp-pro-c1-pod32`) `mode=run` 디스패치 10회 또는 14일 중 먼저 오는 쪽. 원장과 journal에서 센다.
- 용량 거절로 끝난 run 비율 = 종료 코드 3 run 수(journal `role: cloud, outcome: failed`) / 디스패치 수
- flavor 대체 성공 비율 = `create_failed`가 1줄 이상 있으면서 결국 `start`가 있는 run 수 / `create_failed`가 있는 run 수
- 느린 호스트 재발급 횟수와 그 비용(end `slow_host`의 `actual_usd` 합)
- 같은 run id의 `create_failed`가 있는데 journal 줄이 없는 give-up 수(기록 누락)
**한계:** 체인 잡은 `max_minutes: 320`이라 `fits()` 조건 때문에 지연 재시도가 일어나지 않는다. `median_iters_per_s`도 비어 있어 느린 호스트 재발급도 일어나지 않는다. 이 측정창에서 실제로 검증되는 것은 flavor 대체와 기록뿐이다. 재시도·재발급은 측정창에 해당 이벤트가 0건이어도 실패로 보지 않는다.
## 성공 기준 (수치)
- 용량 거절로 끝난 run 비율 ≤ 10%(#373 이전 cpu3c 단일 flavor에서는 거절이면 곧 실패였다)
- 첫 flavor가 거절된 run의 flavor 대체 성공 비율 ≥ 80%
- 기록 누락 0건, 최악 비용 초과 0건(원장 `rate_exceeded` 0건), 11월 지출 상한 $100 미초과
- 재발급이 일어났다면 재발급 1회당 추가 비용 ≤ 잡 최악 비용의 10%
## 롤백 방법
PR #494를 revert하고, 잡 명세를 `cpu_flavor: cpu3c` 단일 flavor로 되돌린다. 원장의 `create_failed` 줄과 journal의 `role: cloud` 줄은 남겨 둔다. `month_total`·`open_entries`·`reap`은 이 줄을 무시하므로 지울 필요가 없다.
## 결과 (측정창 종료 후 기록)
