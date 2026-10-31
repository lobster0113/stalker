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

## 추가 변경 (2026-10-29, #264 / PR #322): 결과를 ops에 게시 + `mode=collect`
- **변경**: `cloud.yml`이 `result_path` 실행의 결과 JSON을 검사(크기 1 MB 이하, `check_result` 비밀 패턴)한 뒤 `ops:cloud/results/<run id>.json`에 올린다. `mode=collect`(`collect_run`, 숫자만)는 파드를 만들지 않고 이전 실행의 아티팩트를 받아 같은 경로로 게시한다(비용 $0).
- **가설**: 에이전트가 아티팩트 blob을 내려받지 않고 ops에서 결과를 읽을 수 있다. 그러면 결과 회수가 실행마다 끊기지 않는다.
- **측정 지표와 측정창**: `result_path` 실행 5회 또는 14일 중 먼저 오는 쪽.
  - `completed`로 끝난 실행 중 `ops:cloud/results/<id>.json`이 푸시된 비율.
  - 그 파일을 ops에서 읽은 에이전트 실행 수(run journal·이슈 코멘트 인용).
  - ops 커밋 크기.
- **성공 기준 (수치)**: 게시율 100%, 비밀 유출 0건, 1 MB를 넘는 ops 결과 커밋 0건.
- **롤백**: `cloud.yml`의 `result to ops`·`fetch earlier result` 단계를 지우거나 PR #322를 revert한다. 이미 올라간 `ops:cloud/results/` 파일은 검사를 통과한 결과이므로 지우지 않고 남긴다(기록 보존).
