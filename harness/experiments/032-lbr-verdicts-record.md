# 032: cloud 결과 게시 뒤 인원별 LBR 판정을 ops:cloud/verdicts에 기록 (record-only)
- 상태: 진행 중
- 제안: builder, 2026-11-05 / 이슈 #576 / PR #578 (ADR 0020)
## 문제 (관측 근거: #572·#574, ops:cloud/results)
#574로 인원별(2–6인) LBR 합격선 판정기(`referee/e3/thresholds.py`)가 생겼지만, 판정은 에이전트가 ops의 결과 파일을 골라
`python -m referee.e3.thresholds <summary.json>...`를 손으로 돌릴 때만 나온다. `by_players`가 있는 mixn 결과가 게시돼도
판정이 어디에도 남지 않아, Planner·Reviewer가 "지금 몇 인에서 합격선을 넘었는가"를 알려면 매번 시드별 최신 run을 직접 골라야 한다
(#576 계획 코멘트: 로컬에서 mixn-c1 전체를 돌리면 seed 1 재실행까지 4시드가 잡힌다 — 수동 선택이 틀리기 쉬운 지점).
## 가설
`launcher.py publish`가 `by_players` 결과를 게시한 직후, 같은 job의 ops 결과 전체(시드마다 run id가 가장 큰 것)를 다시 판정해
`ops:cloud/verdicts/<job>.json`에 덮어쓰면, 인원별 판정이 게시마다 자동으로 최신 상태가 된다.
기록 전용이라(fail·판정 오류여도 exit 0) cloud 잡의 성공률과 비용은 변하지 않는다.
## 변경
- `referee/e3/thresholds.py`: `collect()`(job별·시드별 최신 run), `to_json()`, `verdict()`, `record()`(예외 없이 `error` 필드), CLI `--json`·`--job --results-dir`.
- `harness/cloud/launcher.py`: `publish` 뒤 `record_lbr_verdict()`(판정기를 파일 경로로 로드 — cloud.yml은 패키지를 설치하지 않는다).
- `harness/cloud/push_ledger.sh`: `cloud/verdicts`도 커밋.
- 문서: `referee/GATES.md`, `docs/ARCHITECTURE.md`, `jobs/README.md`.
## 측정 지표와 측정창
머지 후 `by_players`가 있는 결과의 `publish` 3건 또는 14일 중 먼저 오는 쪽. cloud.yml 로그(`lbr verdict ...` 줄)와 ops 커밋에서 센다.
- verdicts 파일 생성률 = `by_players` 게시 중 같은 커밋(또는 같은 run의 push)에 `cloud/verdicts/<job>.json`이 갱신된 비율
- 판정 때문에 실패한 cloud 잡 수 = publish/push ledger 스텝이 판정 코드의 예외로 실패한 run 수
- `error` 필드 건수 = 측정창 안 verdicts 파일 중 `error` 키가 있는 것
- 수동 판정과의 일치 = 측정창 끝에 `python -m referee.e3.thresholds --json --job <job> --results-dir <ops>/cloud/results` 출력과 파일의 `players`가 같은지
**알려진 동작:** `collect()`는 결과 디렉터리에 읽을 수 없는 `<run>.json`이 하나라도 있으면 **job과 무관하게** 이번 판정을 `error`로 만들고,
직전 정상 판정 파일도 `error`로 덮는다. 의도다: 어느 파일이 어느 job인지 읽지 않고는 알 수 없어서, 깨진 파일을 건너뛰면 그 job의 시드가
조용히 빠진 판정이 나올 수 있다. 조용히 틀린 판정보다 드러난 오류가 낫다고 본다. 측정창에 이런 `error`가 생기면 원인 파일을 고치는 것이 해결이다.
## 성공 기준 (수치)
- verdicts 파일 생성률 100%
- 판정 때문에 실패한 cloud 잡 0건
- `error` 필드 0건(위 "알려진 동작"으로 생긴 것은 원인 파일 파손이 확인되면 실패로 세지 않는다)
- 수동 판정과 불일치 0건
## 롤백 방법
PR #578을 revert한다. `ops:cloud/verdicts/` 파일은 남지만 갱신이 멈춘다(지울 필요 없다 — 다른 코드가 읽지 않는다).
수동 판정(`python -m referee.e3.thresholds <summary.json>...`)은 revert 뒤에도 #574 형태로 그대로 쓸 수 있다.
## 결과 (측정창 종료 후 기록)
