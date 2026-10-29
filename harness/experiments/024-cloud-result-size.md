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
## 결과
(측정창 종료 후 auditor가 기록)
