# 021: RunPod 잡 결과를 토큰 경로 HTTP로 회수
- 상태: 진행 중
- 제안: builder, 2026-10-28 / 이슈 #184 / PR #269
## 문제 (관측 근거)
런처(#20, 실험 007)는 파드를 만들고 감시하고 종료한 뒤 비용만 원장에 남긴다. 파드가 만든 결과(요약 JSON, 정책 파일)는 돌아오지 않는다. GPU가 필요한 첫 잡 #264가 이 공백 때문에 막혀 있다. CPU 학습은 `train.yml`(#222, 실험 014)로 옮겨 아티팩트로 회수되지만, GPU 잡에는 그 경로가 없다.
## 가설
파드가 실행마다 만든 128비트 토큰 경로 아래 `status.json`·`result.json`만 `http.server`로 내놓고, 런처가 RunPod HTTP 프록시로 폴링해 받아 오면, 파드에 GitHub 토큰을 주지 않고도 결과를 회수할 수 있다. 추가 비용은 결과가 나온 뒤 다음 폴링까지(≤30초)뿐이다.
## 변경
ADR 0014. `harness/cloud/launcher.py`: 스펙 키 `result_path`, 파드 명령 감싸기, `status.json` 폴링, `check_result`(20 MB 상한, UTF-8 JSON, 비밀 패턴·런처 키·토큰 값 검사), 원장 end 줄에 크기·sha256. `cloud.yml`: 결과를 아티팩트 `cloud-result-<run id>`로 업로드. `jobs/README.md`: 이미지 요구 사항(`python3`).
## 측정 지표와 측정창
첫 `result_path` 잡(#264) 실행부터 5회 또는 머지 후 14일 중 먼저 오는 쪽. 근거는 `cloud.yml` run 로그와 `ops:budget/ledger.jsonl`(CI 전용) 뿐이다.
- `result_path` 잡 중 `completed`(결과 아티팩트 업로드까지) 비율.
- 회수 지연: 파드에 `status.json`이 생긴 시각(파드 명령 종료)부터 런처의 파드 종료 요청까지.
- 결과 대기로 늘어난 비용: 같은 잡의 원장 비용 − (명령 실행 시간 × 시간당 단가).
## 성공 기준 (수치)
- 잡 명령이 0으로 끝난 실행의 `completed` 비율 100%(실패 0건; 실패 시 원인이 이 경로이면 실패로 기록).
- 회수 지연 ≤ 60초(폴링 30초 + 다운로드).
- 결과 대기 추가 비용 ≤ 실행당 $0.05, `budget.json` 상한 위반 0건.
- 결과 아티팩트·로그·원장에 토큰 값이나 키가 나타난 사례 0건.
## 롤백 방법
잡 스펙에서 `result_path`를 빼면 이전 동작(감싸기·포트·폴링 없음)으로 돌아간다. `test_result_job_create_body_and_command`가 `result_path` 없는 스펙의 생성 본문이 바뀌지 않음을 보장한다. 경로 자체가 문제면 PR #269를 revert한다.
## 결과
(측정창 종료 후 auditor가 기록)
