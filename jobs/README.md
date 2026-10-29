# 클라우드 작업 명세

에이전트가 돈을 쓰는 유일한 경로(ADR 0004 §5, #20). **CPU 학습은 여기가 아니라 무료인 `train.yml`(GitHub Actions, #184)에서 돌린다. RunPod은 GPU가 필요한 작업에만 쓴다.** 예외는 CI 러너 기반 예산 추정을 검증하는 1회 측정 `e2-throughput-cpu.yaml`(#264, 최악 $0.12)뿐이다. 작업은 `jobs/<name>.yaml`을 PR로 올리고, 머지 후
`cloud.yml`을 dispatch해서만 실행된다. 키(`RUNPOD_API_KEY`)는 Secret에만 있다.

## 형식 (평면 `key: value`만 — 중첩·목록·여러 줄 없음, ` #` 뒤는 주석)
| 키 | 필수 | 뜻 |
|---|---|---|
| `name` | ✔ | 소문자 `[a-z0-9-]`, pod 이름 `stalker-<name>-<run_id>` |
| `image` | ✔ | 컨테이너 이미지 |
| `command` | ✔ | `bash -lc`로 실행. 끝나면 컨테이너가 종료돼야 한다 |
| `gpu_type` 또는 `cpu_flavor` | 둘 중 하나 | RunPod GPU 타입 ID(`gpu_count`, 기본 1) / CPU flavor ID(`vcpu`, 기본 2) |
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
- 매일 03:17 UTC: `reap` — 기한 지난 `stalker-*` pod 종료, 원장 정리.

## 결과 회수 (`result_path`, #184, ADR 0014)
- 런처가 실행마다 무작위 토큰을 만들어 파드 env `STALKER_RESULT_TOKEN`으로 넘기고, 포트 `8000/http`를 연다.
- 파드 명령은 감싸진다: 먼저 `/<토큰>/` 아래 이름만 답하는 작은 `python3` 서버(런처의 `POD_SERVER`, 표준 라이브러리만)를 띄우고, 런처의 이어 달리기 신호(파일 또는 `none`)를 기다린 뒤 잡 `command`를 실행한다. 끝나면 `result_path`를 복사하고 `status.json`(`{"exit": 코드}`)을 쓴 뒤 대기한다. **이미지에 `python3`가 있어야 한다.** 신호가 20분 안에 오지 않으면 잡을 돌리지 않고 종료 코드 97로 끝난다.
- 런처는 RunPod 프록시(`https://<pod>-8000.proxy.runpod.net/<토큰>/…`)로 상태를 폴링하고, 종료 코드 0이면 결과를 받는다. 받을 때 RunPod 키를 보내지 않는다. 받은 뒤 파드를 종료한다.
- 검사: 20 MB 이하, UTF-8 JSON, 비밀 패턴(GitHub·RunPod·AWS·Slack 토큰, 개인 키, 런처의 키·토큰 값) 없음. 통과하면 워크플로 아티팩트 `cloud-result-<run id>`(30일)로 올라가고, 원장 end 줄에 `result_bytes`·`result_sha256`이 남는다. 1 MB 이하면 같은 JSON이 `ops:cloud/results/<run id>.json`에도 올라간다(런처 `publish`가 다시 검사). 에이전트 샌드박스는 아티팩트 저장소(blob) 호스트에 닿지 못하므로 결과는 `ops`에서 읽는다(#264). 공개 리포의 아티팩트는 로그인한 누구나 받을 수 있으니 결과에 비밀을 넣지 않는다.
- 상태: `completed`(회수 성공), `failed`(명령 종료 코드 ≠ 0, 회수 안 함), `no_result`(결과 파일 없음 또는 회수 전에 파드가 스스로 종료), `result_rejected`(검사 실패, 저장 안 함), `timeout`. `completed` 외에는 실행이 실패로 끝난다.
- 큰 체크포인트는 상한 안의 요약·정책 JSON으로 줄이거나, 재개 가능한 조각으로 나눈다.

## 이어 달리기 (`resume_run`, #354)
- 러너가 `cloud-result-<resume_run>`을 받아 런처에 `--resume-file`로 준다. 런처는 결과를 `RESUME_FIELDS`(잡·tier·인원·모델·체크포인트 등)와 `run_id`만 남겨 gzip으로 줄이고, 파드 서버가 뜨면 RunPod 프록시로 `PUT /<토큰>/resume` 한다. 파드가 받은 바이트 수와 sha256을 돌려주고 런처가 대조한다. `resume_run`이 없으면 `PUT /<토큰>/resume-none`을 보낸다. 파드에는 GitHub 자격 증명이 가지 않는다.
- 파드의 잡 명령은 받은 파일을 `$STALKER_RESUME`으로 본다(없으면 빈 값). pod 잡은 `${STALKER_RESUME:+--resume-result "$STALKER_RESUME"}`로 `pod_train`에 넘긴다. `pod_train`은 잡·tier·인원·`nut_k`가 다르면 거부한다(실패로 끝남). 결과에 `resumed_from_run`과 누적 `iters`가 남는다.
- 업로드 상한 95 MB(`RESUME_MAX_BYTES`): RunPod 프록시 앞의 Cloudflare가 요청 본문을 100 MB에서 끊는다. 서버도 그보다 큰 `Content-Length`는 413으로 거부하고, 런처는 상한을 넘는 결과로는 파드를 만들지 않는다. `pod_train`은 체크포인트를 이 상한 안에 두려고 float64가 넘치면 float32로 저장한다. float32로도 넘치면 결과에는 남지만(`--unpack`용) 이어 달릴 수 없다는 `checkpoint_note`가 붙는다.
- 상태: 파드가 업로드를 거부하거나 받은 내용이 다르면 `resume_failed`.

원장: `ops:budget/ledger.jsonl` (start/end 이벤트). 상한(`harness/budget.json`)을 올리는 PR은 사용자 결정 없이는 금지(reviewer.md).
