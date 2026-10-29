# 026: 파드 학습 이어 달리기 — 결과 서버로 이전 체크포인트 넘기기
- 상태: 진행 중
- 제안: 대화 세션, 2026-10-29 / 이슈 #354
## 문제 (관측 근거)
첫 파드 학습(#333 코멘트, cloud run 40851654734·40851659171, 32 vCPU cpu3c)에서 실제 처리량은 중수 6인 146.7 it/s, 9인 118.0 it/s였다. vCPU당 약 4.6 it/s이고, #321 벤치(705 it/s)의 약 1/5이다. 고수 키는 중수의 약 0.64배 속도라(#325) 파드 1회(학습 240분)에 약 150~200만 회다. ADR 0017 가정상 고수 체인은 약 1,750만 회가 필요하므로 파드를 **약 10회 이어서** 돌려야 한다. 그런데 `pod_train`은 로컬 파일 `--resume`만 받고, 파드는 이전 결과를 받을 길이 없다. 그래서 매 실행이 0회부터 다시 시작한다.
## 가설
파드는 이미 토큰 경로 결과 서버를 RunPod 프록시 뒤에 띄운다(ADR 0014). 같은 서버가 업로드 하나를 받으면 다음이 가능하다.
- 파드에 GitHub 자격 증명을 주지 않는다. 러너가 이전 run의 아티팩트를 받아 런처가 밀어 넣는다.
- 네트워크 볼륨(데이터센터 고정, 월 저장비, 회수용 S3 키)이 필요 없다.

업로드가 Cloudflare 본문 한도(100 MB) 안이면 고수 체인 10회를 사람 개입 없이 `resume_run`만 바꿔 이어 갈 수 있다. 근거: 중수 결과는 3.7~5.7 MB(base64 포함)이고, 고수는 #346 추정으로 수십 MB다.
## 변경
- `harness/cloud/launcher.py`
  - `http.server` 대신 표준 라이브러리 핸들러 `POD_SERVER`를 쓴다.
    - GET은 `/<토큰>/status.json`·`result.json`만 답한다.
    - PUT/POST `/<토큰>/resume`는 `Content-Length` ≤ `RESUME_MAX_BYTES`(95 MB)만 받는다. 넘으면 413이다. 끝까지 받은 뒤 rename하고, 바이트 수와 sha256을 돌려준다.
    - `/<토큰>/resume-none`은 "없음" 신호다.
    - 신호는 한 번만 받는다(이후 409).
  - 감싼 파드 명령은 신호(최대 `RESUME_WAIT_S` 20분)를 기다린 뒤 잡을 실행한다. 받은 파일은 `$STALKER_RESUME`으로 넘긴다. 신호가 없으면 잡을 돌리지 않고 종료 코드 97로 끝난다.
  - `run_job(resume=...)`은 프록시가 열릴 때까지(502 → 재시도) 업로드한다. 받은 sha256이 다르거나 거부되면 상태를 `resume_failed`로 기록하고 파드를 종료한다. 결과 폴링은 신호 뒤에만 한다.
  - `resume_payload`는 이전 결과를 다시 검사한다(`check_result`). 그다음 `RESUME_FIELDS`와 `run_id`만 남기고 gzip으로 줄인다. base64의 4/3 부풀림은 gzip이 대부분 되돌린다. 95 MB를 넘으면 **파드를 만들기 전에** 거부한다. `--resume-file`·`--resume-run`은 함께 써야 한다. dry run에서도 크기를 검사한다.
- `.github/workflows/cloud.yml`
  - 입력 `resume_run`을 env로만 받는다. 셸에서 숫자인지 검사한다.
  - `actions/download-artifact@v4`(run-id, github-token)로 `cloud-result-<id>`를 `$RUNNER_TEMP/resume/`에 받는다.
  - 런처에 `--resume-file`·`--resume-run`을 넘긴다. 원장·예산 동작은 그대로다.
- `stalker/tools/pod_train.py`
  - `--resume-result`(평문 또는 gzip JSON)를 받는다. 잡·tier·인원·`model.k/n/depth`·`nut_k`·게임 규칙(#339의 `menu`·`raise_cap`, 없으면 v1·3으로 읽음)이 다르면 고치는 방법과 함께 거부한다. 규칙은 `--menu`·`--no-raise-cap`으로 정하며 기본값은 v1·3이다.
  - 결과에 `resumed_from_run`을 남긴다. `iters`는 누적되고 `resumed_from`은 이어 받은 반복 수다.
  - 체크포인트는 float64가 업로드 한도(`RESUME_BUDGET` = 런처 상한, 테스트로 고정)를 넘으면 float32로 저장한다. float32로도 넘치면 결과 상한(250 MB) 안에서 저장하되 `checkpoint_note`에 "이어 달릴 수 없음"을 적는다.
  - 기존 `--resume`(CI ckpt)은 그대로다.
- `jobs/e3-tp-*-pod32.yaml`: `${STALKER_RESUME:+--resume-result "$STALKER_RESUME"}`를 추가한다.
- 테스트
  - 가짜 프록시: 업로드 → 실행, 502 재시도, 신호 없음(`resume-none`), 413·404·sha 불일치 → `resume_failed`, 409(응답 유실) → 계속.
  - 실제 서버 프로세스: 상한 초과 거부, 토큰 밖 404, 신호 1회.
  - Linux bash: 신호 전에는 잡이 시작하지 않는다. 업로드 파일이 잡에 보인다. 신호가 없으면 97이다.
  - `pod_train`: 왕복(학습 → 결과 → 런처 페이로드 → 이어 학습, 반복 누적, `resumed_from_run`), 불일치 거부.
## 알려진 한계
- 100 MB 한도는 Cloudflare 문서 기준의 가정이다. 실측은 실제 파드가 있어야 하므로 머지 후에만 할 수 있다(아래 "프록시 본문 한도 실측 계획").
- float32로 이어 가면 비트 단위 재현은 아니다(pod_train 문서). float32로도 95 MB를 넘는 모델은 이 방법으로 넘길 수 없다. 그때는 (b) 네트워크 볼륨이나 분할 업로드를 다시 검토한다.
- 신호를 기다리느라 잡 시작이 첫 폴링(최대 30초)만큼 늦어진다.
## 프록시 본문 한도 실측 계획 (머지 후 첫 `resume_run` 실행)
머지 전에는 실측할 수 없다. 실제 RunPod 파드와 그 프록시가 필요하고 비용이 든다. 그래서 #354 수용 기준(고수 체인 2회)의 2회차를 측정으로 쓴다.
- 방법
  - 런처 로그 `resume: sent N bytes`를 본다. 이 줄은 파드가 돌려준 바이트 수와 sha256이 보낸 값과 같을 때만 찍힌다(`_signal`).
  - 같은 run 로그에서 dry run의 `dry run: resume upload N bytes ok`, 원장 `minutes`, 업로드 시간(신호 전후 로그 시각)을 함께 읽는다.
  - 크기가 한도에 가까운지 보려면 1회차 결과의 npz 크기(결과 `checkpoint.b64` 길이 × 3/4)와 비교한다.
- 기록 위치: 이슈 #354 코멘트. run id, N, sha 일치 여부, 업로드 시간, 상태를 적고, 이 문서의 "결과"에도 옮긴다.
- 성공 판정: 상태 `completed`, 2회차 결과의 `resumed_from` = 1회차 `iters`.
- 실패 시 대응
  - 413(Cloudflare 또는 파드)이나 업로드 시간 초과로 `resume_failed`·`timeout`이 나면 다음 순서로 대응한다.
  - (1) 이어 달릴 페이로드를 줄인다. `pod_train`이 float32로 저장하게 `RESUME_BUDGET`을 낮추고, 그래도 크면 regret만 담는 페이로드(average 합계 제외)를 넣는다.
  - (2) 실측 한도 아래로 `RESUME_MAX_BYTES`와 `RESUME_BUDGET`을 함께 낮춘다. 같은 값이어야 한다는 것은 테스트로 고정돼 있다.
  - (3) 그래도 안 되면 분할 업로드나 (b) 네트워크 볼륨을 새 이슈로 검토한다.
  - 실패한 run의 비용과 원인은 #354 코멘트에 남긴다.

## 측정 지표와 측정창
머지 후 `resume_run`을 쓴 파드 실행 5회 또는 14일 중 먼저 오는 쪽. 근거는 cloud.yml 로그, 결과 아티팩트·`ops:cloud/results`, `ops:budget/ledger.jsonl`뿐이다.
- 이어 달린 실행의 `resumed_from` = 이전 결과의 `iters`, `resumed_from_run` = 이전 run id.
- 업로드 크기(로그)와 성공 여부. `resume_failed`·exit 97 건수.
- 신호 대기로 늘어난 시간: 원장 `minutes`와 학습 `train_seconds`의 차.
## 성공 기준 (수치)
- 고수 파드 체인 2회 연속 성공(#354 수용 기준). 2회차의 `resumed_from` = 1회차 `iters`이고 `iters` > 1회차.
- 같은 2회차에서 업로드 크기 N과 sha 일치가 #354 코멘트에 기록됨(프록시 한도 실측).
- 측정창 안 `resume_failed` 0건, 신호 시간 초과(97) 0건.
- 원장·예산 동작 변화 없음: 모든 start에 end가 있고 월 합계 ≤ 상한.
## 롤백 방법
이 PR을 revert한다. 파드 서버는 `http.server`로, 잡 명령은 처음부터 학습으로 돌아간다. 이미 받은 결과 아티팩트는 `--unpack`·CI `resume_run`으로 계속 쓸 수 있다.
## 정정 (#361, 2026-10-29)
- 첫 실사용 run 40886839070(고수 체인 2회차)이 파드 생성 5초 뒤 `resume refused by the pod (HTTP 404)`로 끝났다($0.0013). RunPod 프록시는 포트가 연결되기 전에 502가 아니라 404를 준다.
- `_signal`이 404도 "아직 부팅 중"으로 보고 다시 시도한다. 파드 서버의 404는 런처가 보내지 않는 경로에만 나오므로 오인 위험이 없다. 재시도 상한은 파드 쪽 `RESUME_WAIT_S` 뒤 exit 97(EXITED)이다.
- #356 이후 모든 파드 잡이 신호(`resume-none` 포함)를 보내므로 이 수정 전에는 파드 실행이 모두 시작 직후 실패했다. 이 run은 측정창의 `resume_failed` 건수에서 뺀다(수정 전 결함).

## 결과
(측정창 종료 후 auditor가 기록)
