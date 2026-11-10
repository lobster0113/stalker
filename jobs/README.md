# 클라우드 작업 명세

에이전트가 돈을 쓰는 유일한 경로(ADR 0004 §5, #20). **CPU 학습은 여기가 아니라 무료인 `train.yml`(GitHub Actions, #184)에서 돌린다. RunPod은 GPU가 필요한 작업에만 쓴다.** 예외는 CI 러너 기반 예산 추정을 검증하는 1회 측정 `e2-throughput-cpu.yaml`(#264, 최악 $0.12)뿐이다. 작업은 `jobs/<name>.yaml`을 PR로 올리고, 머지 후
`cloud.yml`을 dispatch해서만 실행된다. 키(`RUNPOD_API_KEY`)는 Secret에만 있다.

## 형식 (평면 `key: value`만 — 중첩·여러 줄 없음, 목록은 아래 세 키의 한 줄 `[a, b]`뿐, ` #` 뒤는 주석)
| 키 | 필수 | 뜻 |
|---|---|---|
| `name` | ✔ | 소문자 `[a-z0-9-]`, pod 이름 `stalker-<name>-<run_id>` |
| `image` | ✔ | 컨테이너 이미지 |
| `command` | ✔ | `bash -lc`로 실행. 끝나면 컨테이너가 종료돼야 한다 |
| `gpu_type`·`cpu_flavor`·`cpu_flavors` | 셋 중 하나 | RunPod GPU 타입 ID(`gpu_count`, 기본 1) / CPU flavor ID(`vcpu`, 기본 2) / 순서 있는 CPU flavor 목록 `[cpu5c, cpu3c]`(`vcpu: 32` 필수, 아래 "용량과 느린 호스트") |
| `flavor_hourly_usd` | | flavor별 단가 상한 목록(flavor 수만큼, 각각 ≤ `hourly_usd`). 없으면 모두 `hourly_usd` |
| `median_iters_per_s` | | flavor별 이 잡의 실측 중앙 it/s 목록(0 = 검사 안 함). `result_path` 필요 |
| `max_minutes` | ✔ | 최대 시간(≤330: GitHub 러너 잡 한도 360분 안에서 종료·원장 push까지 끝나야 함). 넘으면 종료. 더 긴 학습은 재개 가능한 조각으로 나눈다 |
| `hourly_usd` | ✔ | 허용 단가 상한. 실제 단가가 더 높으면 즉시 종료 |
| `est_cost_usd` | | 예상 비용. 예산 검사는 `max(est_cost_usd, hourly_usd × max_minutes / 60)`(최악)로 한다 |
| `disk_gb` | | 기본 20 |
| `cloud` | | `COMMUNITY`(기본) 또는 `SECURE` |
| `result_path` | | 잡이 쓰는 결과 JSON의 절대 경로(`[A-Za-z0-9._/-]`). 설정하면 런처가 회수한다(아래 "결과 회수") |

## 실행 (MCP `actions_run_trigger`, workflow `cloud.yml`, ref `main`)
- `mode=check`: 키 유효성·잔액 조회(비용 0). 키 이상이면 `ops:NEEDS_HUMAN.md`에 재등록 요청.
- `mode=run job=jobs/x.yaml dry_run=true`: 예산 검사만, pod 생성 없음.
- `mode=run job=jobs/x.yaml`: 실제 실행. pod 생성 직후 start(예약) 줄을 ops에 push하고, push가 실패하면 pod를 종료하고 실패로 끝난다. 월 누적(종료분은 실제, 진행분은 최악 예약) + 최악 비용 > `harness/budget.json` 상한이면 거부(exit 2).
- `mode=run job=jobs/x.yaml resume_run=<run id>`: 앞선 같은 잡 실행의 결과(아티팩트 `cloud-result-<run id>`)에서 이어 학습한다(#354, 아래 "이어 달리기"). `dry_run=true`와 함께 쓰면 받은 결과가 넘길 수 있는 크기인지만 본다.
- `mode=collect collect_run=<run id>`: 앞선 `run`의 아티팩트 `cloud-result-<run id>`를 받아 `ops:cloud/results/<run id>.json`에 올린다(비용 0). `ops`에 결과가 없는 예전 실행용이다.
- `mode=export export_run=<run id> tier=<등급>`: 앞선 mixn c1 `run`의 아티팩트 `cloud-result-<run id>`를 러너에서 받아 `python -m stalker.tools.export_web_players export`로 2·3·4·5·6인 웹 정책 파일(`<등급>-<n>.json`)과 `web/app/policy/index.json` 갱신본을 만들고 아티팩트 `web-policy-<run id>`(30일)로 올린다(#588, ADR 0021 후속 2). 파드를 띄우지 않고 원장 줄도 남기지 않는다(`cloud-budget` 그룹). 파일별 `keys`·`players`·`bytes`·`sha256`·`lbr_bb`·`within_page_budget`(3MB 페이지 상한 이하인가)·`keys_by_min_visits`(`--min-visits` 문턱 1·2·3·4·5·10·20·50·100별 남는 키 수, `VISIT_STEPS`)와 `index.json`의 바이트·sha256 요약이 `ops:cloud/exports/<run id>.json`에 올라간다 — 에이전트는 이 파일로 결과를 본다. 선택 입력 `export_strategy`(`current`|`average`, 기본 current)·`export_min_visits`(기본 0)·`export_min_visits_by_players`(예 `2:10,3:5,4:5,5:5,6:2`, 기본 빈 문자열 = 없음; 지정한 인원만 그 문턱, 나머지는 `export_min_visits`; 파일별 실제 값은 요약 `files[].min_visits`). 3MB 페이지 상한 안의 파일만 `index.json`(그 파일들만 나열)과 함께 `ops:cloud/policies/<run id>/`에 올라가고, 상한을 넘은 파일은 요약에만 남는다(run은 실패하지 않음, #596). 에이전트는 이 경로에서 읽어 다음 PR로 `web/app/policy/`에 옮긴다. main·`web/app/policy/`에는 커밋하지 않는다(정책 교체는 별도 PR). 아티팩트가 없거나 만료되면 첫 오류 줄이 `artifact cloud-result-<id> not found/expired: 다시 학습하거나 다른 run을 지정`으로 실패한다. `player_mix`가 없는 결과는 고치는 방법(`export_web_policy --pod-result`)과 함께 거부된다.
- 매일 03:17 UTC: `reap` — 기한 지난 `stalker-*` pod 종료, 원장 정리.

## 웹 정책 LBR 잡 (`web-policy-lbr-mid.yaml`, #661)
- 서비스가 쓰는 걸러 낸 정책(`ops:cloud/policies/<run>/mid-{2..6}.json`)을 ADR 0020 핸드 수(2·3인 2,000 / 4·5인 600 / 6인 1,000)·시드(1, 2 → 평가 시드 10001·10002)로 백오프 끔/켬 두 번씩 잰다. 디스패치: `mode=run job=jobs/web-policy-lbr-mid.yaml`(먼저 `dry_run=true`). 다른 정책 run이면 명세의 `POLICY_RUN`을 바꾸는 PR.
- 예상 비용: cpu5c 32 vCPU $1.2/h × 약 40~90분 ≈ $1~2, 최악 $3.00(`max_minutes: 150`). 결과: `ops:cloud/results/<run id>.json`의 `backoff.on|off.<n>`(`lbr_bb`·`lbr_stderr_bb`·`limit`·`pass`).
- `web-policy-lbr-pages.yaml`(#697): `-s3`와 같되 정책 run 하나 대신 main의 서비스 페이지 `web/app/policy/mid-{2..6}.json`을 그대로(`--from-pages`, 시드 1~3) 잰다. 칸마다 그 파일의 `run_id`가 `policy_run`으로 남아 `e3_web_lbr`의 인원별 `fresh` 판정에 쓰인다(#695). 레거시(c1 아님) 페이지 인원은 backoff=on 칸을 만들지 않고 결과 `legacy_pages`에 적힌다(#702). 최악 $3.00.
- `web-policy-lbr-mid-s4long.yaml`(#708): `web-policy-lbr-mid.yaml`과 같되 `POLICY_RUN=42591543123`(120k, #714 재-export)과 결과 파일 이름만 다르다. 최악 $3.00.

## 결과 회수 (`result_path`, #184, ADR 0014)
- 런처가 실행마다 무작위 토큰을 만들어 파드 env `STALKER_RESULT_TOKEN`으로 넘기고, 포트 `8000/http`를 연다.
- 파드 명령은 감싸진다: 먼저 `/<토큰>/` 아래 이름만 답하는 작은 `python3` 서버(런처의 `POD_SERVER`, 표준 라이브러리만)를 띄우고, 런처의 이어 달리기 신호(파일 또는 `none`)를 기다린 뒤 잡 `command`를 실행한다. 끝나면 `result_path`를 복사하고 `status.json`(`{"exit": 코드}`)을 쓴 뒤 대기한다. **이미지에 `python3`가 있어야 한다.** 신호가 20분 안에 오지 않으면 잡을 돌리지 않고 종료 코드 97로 끝난다.
- 런처는 RunPod 프록시(`https://<pod>-8000.proxy.runpod.net/<토큰>/…`)로 상태를 폴링하고, 종료 코드 0이면 결과를 받는다. 받을 때 RunPod 키를 보내지 않는다. 받은 뒤 파드를 종료한다.
- 검사: 20 MB 이하, UTF-8 JSON, 비밀 패턴(GitHub·RunPod·AWS·Slack 토큰, 개인 키, 런처의 키·토큰 값) 없음. 통과하면 워크플로 아티팩트 `cloud-result-<run id>`(30일)로 올라가고, 원장 end 줄에 `result_bytes`·`result_sha256`이 남는다. 1 MB 이하면 같은 JSON이 `ops:cloud/results/<run id>.json`에도 올라간다(런처 `publish`가 다시 검사). 에이전트 샌드박스는 아티팩트 저장소(blob) 호스트에 닿지 못하므로 결과는 `ops`에서 읽는다(#264). 결과에 `by_players`가 있으면 그 job의 인원별 LBR 판정표가 `ops:cloud/verdicts/<job>.json`에 덮어써진다(기록 전용, #576). 공개 리포의 아티팩트는 로그인한 누구나 받을 수 있으니 결과에 비밀을 넣지 않는다.
- 상태: `completed`(회수 성공), `failed`(명령 종료 코드 ≠ 0, 회수 안 함), `no_result`(결과 파일 없음 또는 회수 전에 파드가 스스로 종료), `result_rejected`(검사 실패, 저장 안 함), `timeout`. `completed` 외에는 실행이 실패로 끝난다.
- 큰 체크포인트는 상한 안의 요약·정책 JSON으로 줄이거나, 재개 가능한 조각으로 나눈다.
- CI 학습 잡(`stalker/train_jobs.py`)의 표 파일은 gzip이다(#560): `<잡>-seed<시드>.policy.json.gz`·`.ckpt.json.gz`. 시드당 256MiB 한도(`ARTIFACT_MAX_BYTES`)와 `_drop_tables`는 압축 뒤 바이트로 판단한다. resume과 `export_web_policy`·`preflop_rows`·`pod_train --resume`은 `.json.gz`와 이전의 평문 `.json`을 모두 읽는다(`stalker/jsonio.py`).

## 이어 달리기 (`resume_run`, #354)
- 러너가 `cloud-result-<resume_run>`을 받아 런처에 `--resume-file`로 준다. 런처는 결과를 `RESUME_FIELDS`(잡·tier·인원·모델·체크포인트 등)와 `run_id`만 남겨 gzip으로 줄이고, 파드 서버가 뜨면 RunPod 프록시로 `PUT /<토큰>/resume` 한다. 파드가 받은 바이트 수와 sha256을 돌려주고 런처가 대조한다. `resume_run`이 없으면 `PUT /<토큰>/resume-none`을 보낸다. 파드에는 GitHub 자격 증명이 가지 않는다.
- 파드의 잡 명령은 받은 파일을 `$STALKER_RESUME`으로 본다(없으면 빈 값). pod 잡은 `${STALKER_RESUME:+--resume-result "$STALKER_RESUME"}`로 `pod_train`에 넘긴다. `pod_train`은 잡·tier·인원·`nut_k`가 다르면 거부한다(실패로 끝남). 결과에 `resumed_from_run`과 누적 `iters`가 남는다.
- 업로드 상한 95 MB(`RESUME_MAX_BYTES`): RunPod 프록시 앞의 Cloudflare가 요청 본문을 100 MB에서 끊는다. 서버도 그보다 큰 `Content-Length`는 413으로 거부하고, 런처는 상한을 넘는 결과로는 파드를 만들지 않는다. `pod_train`은 체크포인트를 이 상한 안에 두려고 float64가 넘치면 float32로 저장한다. float32로도 넘치면 결과에는 남지만(`--unpack`용) 이어 달릴 수 없다는 `checkpoint_note`가 붙는다.
- 상태: 파드가 업로드를 거부하거나 받은 내용이 다르면 `resume_failed`.

## 용량과 느린 호스트 (#401, ADR 0019 §6)
- **flavor 대체.** 런처는 목록 순서대로 하나씩 pod를 만든다. RunPod가 HTTP 500 "no longer any instances available"(용량 부족, 비용 0)로 거절하면 다음 flavor로 바로 다시 만든다. 단가 검사는 실제로 잡힌 flavor의 `flavor_hourly_usd`로 한다.
- **지연 재시도.** 목록이 모두 용량 부족이면 15·30·60분 기다렸다가 목록을 다시 돈다(최대 3회). 거절마다 원장에 `create_failed` 줄(`run_id`·`flavor`·`attempt`, `actual_usd` 0)이 남는다. 다 실패하면 run id가 든 메시지로 종료 코드 3. 다음 디스패치 판단은 그 줄을 보고 한다.
- **느린 호스트 재발급.** `result_path` 잡의 stderr는 파드 안 `job.log`로도 복사되고, 결과 서버가 첫 진행 줄의 `iters_per_s` 숫자 하나만 `/<토큰>/progress.json`으로 내준다(로그 본문은 나가지 않는다). `median_iters_per_s`가 있고 그 값이 중앙값의 0.6배 미만이면 그 pod를 종료(원장 end `status: slow_host`, 실제 비용)하고 예산을 다시 검사한 뒤 **한 번만** 다시 만든다. 새 pod도 느리면 그대로 돌린다. 결과에 `replaced_pods`가 남는다.
- **벽시계 한도.** 기다림과 재발급은 그 뒤 pod가 `max_minutes`를 다 써도 런처 시작부터 330분(`MAX_JOB_MINUTES`) 안에 끝날 때만 한다. GitHub 러너가 360분에 잡을 죽이면 종료·원장 기록이 안 되기 때문이다. 그래서 `max_minutes: 320` 잡은 flavor 대체만 하고 지연 재시도는 못 한다(15분 대기도 넘친다). 재발급은 pod 시작 후 약 10분 안에 결정될 때만 들어간다.

원장: `ops:budget/ledger.jsonl` (start/end 이벤트, 용량 거절은 `create_failed`). 상한(`harness/budget.json`)을 올리는 PR은 사용자 결정 없이는 금지(reviewer.md).
