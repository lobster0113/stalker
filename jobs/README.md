# 클라우드 작업 명세

에이전트가 돈을 쓰는 유일한 경로(ADR 0004 §5, #20). 작업은 `jobs/<name>.yaml`을 PR로 올리고, 머지 후
`cloud.yml`을 dispatch해서만 실행된다. 키(`RUNPOD_API_KEY`)는 Secret에만 있다.

## 형식 (평면 `key: value`만 — 중첩·목록·여러 줄 없음, ` #` 뒤는 주석)
| 키 | 필수 | 뜻 |
|---|---|---|
| `name` | ✔ | 소문자 `[a-z0-9-]`, pod 이름 `stalker-<name>-<run_id>` |
| `image` | ✔ | 컨테이너 이미지 |
| `command` | ✔ | `bash -lc`로 실행. 끝나면 컨테이너가 종료돼야 한다 |
| `gpu_type` 또는 `cpu_flavor` | 둘 중 하나 | RunPod GPU 타입 ID(`gpu_count`, 기본 1) / CPU flavor ID(`vcpu`, 기본 2) |
| `max_minutes` | ✔ | 최대 시간(≤1440). 넘으면 종료 |
| `hourly_usd` | ✔ | 허용 단가 상한. 실제 단가가 더 높으면 즉시 종료 |
| `est_cost_usd` | | 예상 비용. 예산 검사는 `max(est_cost_usd, hourly_usd × max_minutes / 60)`(최악)로 한다 |
| `disk_gb` | | 기본 20 |
| `cloud` | | `COMMUNITY`(기본) 또는 `SECURE` |

## 실행 (MCP `actions_run_trigger`, workflow `cloud.yml`, ref `main`)
- `mode=check`: 키 유효성·잔액 조회(비용 0). 키 이상이면 `ops:NEEDS_HUMAN.md`에 재등록 요청.
- `mode=run job=jobs/x.yaml dry_run=true`: 예산 검사만, pod 생성 없음.
- `mode=run job=jobs/x.yaml`: 실제 실행. 월 누적(종료분은 실제, 진행분은 최악 예약) + 최악 비용 > `harness/budget.json` 상한이면 거부(exit 2).
- 매일 03:17 UTC: `reap` — 기한 지난 `stalker-*` pod 종료, 원장 정리.

원장: `ops:budget/ledger.jsonl` (start/end 이벤트). 상한(`harness/budget.json`)을 올리는 PR은 사용자 결정 없이는 금지(reviewer.md).
