# 024: RunPod 결과 한도 20MB → 256MB — 파드 학습 모델 회수
- 상태: 진행 중
- 제안: 대화 세션, 2026-10-29 / 이슈 #346
## 문제 (관측 근거)
#333 파드 학습(`stalker/tools/pod_train.py`)은 모델을 결과 JSON에 담아서만 회수할 수 있다. 파드에는 GitHub 자격 증명이 없고, 런처가 RunPod 프록시로 `result.json` 하나만 당겨 온다. CI 고수 `e3-tp-pro-w4` 10⁵회(run 40815871622)가 이미 37.2만 키, 체크포인트 JSON 85MB다. 파드 1회(4시간, 수백만 회)는 이보다 크다. 20MB 한도에서는 npz float32로 줄여도 넘칠 가능성이 크고, 넘치면 학습 비용(약 \$4)을 쓰고도 모델을 잃는다.
## 가설
한도를 256MB로 올리면 파드 학습 결과(npz float64 또는 float32, base64)를 그대로 회수할 수 있다. 회수한 결과는 지금처럼 아티팩트에만 남는다(ops 게시 한도 1MB는 그대로). 대화 세션이 받아서 `--unpack`으로 CI 형식으로 복원한다.
## 변경
- `harness/cloud/launcher.py`: `RESULT_MAX_BYTES` 256MB. `check_result`의 기본 한도는 호출 시점의 상수를 읽는다(테스트에서 작은 한도로 바꿔 끼우려고).
- `stalker/tools/pod_train.py`: 결과 예산 250MB.
- 테스트: 21MB 본문 통과, 한도 초과 거부(작은 한도로 확인).
## 측정 지표와 측정창
머지 후 첫 파드 학습 3회 또는 7일 중 먼저 오는 쪽. 근거는 cloud.yml 로그와 원장(`ops:budget/ledger.jsonl`의 `result_bytes`, status).
- 결과 회수 성공 여부(status `completed`)와 `result_bytes`.
- 결과 수집 단계 시간(런처 로그의 pod 종료 직전 시각 차).
## 성공 기준 (수치)
- 파드 학습 run의 결과 회수 100% (`result_rejected`·`no_result` 0건, 크기 사유).
- 수집 단계 ≤ 5분.
## 롤백 방법
이 PR을 revert하면 20MB로 돌아간다. 파드 학습은 요약만 남기고 모델을 잃게 된다(`checkpoint_note`).
## 중간 관측 (#346 기준 2, builder 2026-10-29)
근거: cloud.yml run 로그(launcher 단계 `result saved:` 줄)와 `ops:budget/ledger.jsonl` end 줄. 머지(PR #347, 07:29Z) 후 파드 학습 3회.

| run | 잡 | 학습 시간 | 결과 회수 | result_bytes | 원장 status |
|---|---|---|---|---|---|
| 40840669062 | e3-tp-pro-pod32 | 244.8분 | 성공 (artifact `cloud-result-40840669062`, zip 10,160,611 B) | 13,648,456 | `reaped` — end 줄 push 충돌(#351 이전 커밋, #358). 런처 로그는 `completed` |
| 40851654734 | e3-tp-mid-pod32 | 95.83분 | 성공 | 3,735,531 | `completed` |
| 40851659171 | e3-tp-mid9-pod32 | 92.56분 | 성공 | 5,724,611 | `completed` |

- 크기 사유의 `result_rejected`·`no_result` 0건. 3회 모두 회수했다.
- 고수 결과 13.6MB는 옛 한도 20MB 안이었다(이슈의 85MB 추정은 CI JSON 체크포인트 기준. 파드 결과는 npz 압축이라 작다). 키가 더 늘어나는 체인 후속 회차(#354)에서 20MB를 넘을 수 있어 256MB 한도는 유지한다.
- 1MB 초과라 3건 모두 ops에는 게시되지 않고 아티팩트에만 있다(`result is ... bytes > 1048576 for ops`). 루틴 세션은 아티팩트 blob 호스트가 프록시 403이라 직접 못 읽는다 → #358.
- 수집 단계 시간: 런처가 학습 종료와 결과 수신을 따로 찍지 않아 로그로 분리 측정할 수 없다. 고수 run에서 결과 저장 직후 업로드까지 4초(12:18:58→12:19:02). 측정하려면 런처에 단계 시각 로그가 필요하다(후속).
## 결과
(측정창 종료 후 auditor가 기록)
