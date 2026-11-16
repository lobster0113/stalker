# E F5 1회차 결과: 4인 버블 SNG(503020, 순수 ICM, cold) (#901)

> 수치 출처: 클라우드 run 43735226442 (`cloud.yml mode=run`, main 16b8941e)의 `ops:cloud/results/43735226442.summary.json`과 `ops:budget/ledger.jsonl`. 사람이 직접 돌린 값 없음.

## 설정
잡 `e3-tp-mid-c1-sng-bubble-pod32`: tier mid, 4인(9max_sng_503020 생존 4명, stage b, level 0), c1 키, real 메뉴, payoff icm(payouts .5/.3/.2), λ=0, `--stacks bubble:skewed`, 시드 1, 16 workers, batch 500, `--max-iters 20000`, LBR 600핸드.
- 종료: `stopped_by=max_iters` (20,000 iter, 학습 1,689.5초 = 28분, 11.84 it/s). 60분 상한에는 닿지 않음.
- 정책 sha256 `e886939c…1cd1da`, regret sha256 `d7073e1e…e2be`, train_env `1261657cabcdc1ad`, infosets 652,811.

## LBR (bb 단위, 600핸드, 시드 10001) — 주의: 단위가 bb이지 ICM 단위가 아니다
| 평가 | lbr_bb | stderr |
|---|---|---|
| 기본(`lbr`) | 3.161 | 0.671 |
| average | 2.966 | 0.669 |
| offmenu | 3.125 | 0.672 |
좌석별(기본): EP0 5.07 · BTN 3.60 · SB 2.76 · BB 1.21. 학습 보상(ICM)과 평가 단위(bb)가 달라 cash 칸 기준선과 직접 비교하지 않는다(ICM 단위 LBR은 F4b).

## 커버리지
키 수 대부분이 방문 10회 미만(under10): 예) `fca` 153,461 중 148,858, `ka` 57,278 중 54,328. 20k iter·cold 학습의 희소성이 크다. 기준값 대비 의미는 F6·F7에서 판단.

### key 분포(`t`·`n` 칸별) — 직접 확인 못 함 (#901 기준 3 부분 충족)
- summary에는 행동 이력 버킷별 coverage만 있고 `t`·`n` 칸별 key 수 분해가 없다. 결과 체크포인트(result sha256 `0a71d5b7…`, 49MB)는 ops에 올라가지 않고(1MB 초과, `b64.omitted`) 아티팩트 `cloud-result-43735226442`로만 있는데, 이 실행 환경에서는 blob 다운로드가 프록시에 막혀 key 목록을 산출하지 못했다. 따라서 "`t b0`·`n4` 칸만 있다"는 **직접 확인되지 않았다**.
- 간접 근거(직접 확인 아님): `model.n=4`, `train_env.stage=b`, `train_env.level_index=0`, `stack_remaining=4`는 학습이 단일 환경(생존 4명·stage b·level 0)에서 돌았음을 가리킨다.
- 후속 제안: summary에 `t`·`n` 칸별 key 수를 넣는 이슈(pod_train summary, area:ai). 산출 명령은 체크포인트를 받을 수 있는 환경에서 key 문자열을 칸별로 센다.

## 비용·시간
원장: 30.81분, 실제 $0.4929 (예약 $3.60). 11월 합계는 이전 $28.61 + $0.49. LBR 시간 84초(600핸드).

## 메모
- summary의 `"job": "e3-tp-mid4-c1-pod"`는 잡 이름 `e3-tp-mid-c1-sng-bubble-pod32`와 다르다. pod_train 기본 job 이름이 그대로 기록된 것으로 보이며(미확인), 후속 이슈 후보.

## 다음 (후속 제안)
- F4b: ICM 단위 LBR(착수 조건 충족), F6·F7(λ 선택)은 이 결과를 입력으로 사용.
- 2회차 재디스패치는 불필요(exit 0, stopped_by max_iters).
- 리뷰어 메모: `test_job_flags_parse_with_pod_train`이 argv만 만들고 파싱하지 않음(비차단, 별도 이슈 후보).
- 다음 run부터 결과 summary의 `key_cells`(`t`: 토너먼트 칸별·`n`: 인원별 정보집합 수, #920)로 학습한 칸을 확인한다.
