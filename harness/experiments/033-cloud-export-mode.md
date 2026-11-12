# 033: cloud.yml `mode=export` — mixn c1 결과를 2–6인 웹 정책 아티팩트·ops 요약으로 (record-only)
- 상태: 진행 중
- 제안: builder, 2026-11-05 / 이슈 #588 / PR #590 (ADR 0021 후속 2)
## 문제 (관측 근거: #585·#586, ADR 0021, STATE 11-05 11:40Z)
#585로 `export_web_policy --players`가 mixn c1 정책을 인원별 파일로 나눌 수 있게 됐지만, 원본 결과(`cloud-result-<run>` 아티팩트)는
cloud.yml 러너에서만 받을 수 있고 로컬 루틴은 아티팩트 zip이 프록시 403으로 막힌다(STATE 경보 11-05 10:20Z "아티팩트 zip 403").
그래서 M2–M4 run의 인원별 정책은 지금 아무도 만들 수 없고, 그 아티팩트는 ~12-03에 만료된다.
## 가설
cloud.yml에 파드도 원장 줄도 없는 `mode=export`를 두어 러너가 아티팩트를 받아 `export_web_players export`를 돌리고,
결과 파일은 `web-policy-<run>` 아티팩트로, 요약(키 수·바이트·sha256·LBR·3MB 상한 여부)은 `ops:cloud/exports/<run>.json`으로 올리면,
에이전트가 로컬 다운로드 없이 ops 요약만으로 정책 크기·품질을 판단하고 다음 PR(정책 커밋)을 계획할 수 있다.
러너만 쓰므로 클라우드 지출은 0이고, 기존 모드(check·run·reap·collect)의 동작은 바뀌지 않는다.
## 변경
- `.github/workflows/cloud.yml`: 입력 `export_run`·`tier`·`export_strategy`·`export_min_visits`, `export` 케이스 입력 검증,
  `check export artifact` → `fetch export source` → `export web policies` → `upload web policies` 스텝(모두 `env.MODE == 'export'`).
- `harness/cloud/push_ledger.sh`: `cloud/exports`도 커밋.
- `stalker/tools/export_web_players.py`(신규), `stalker/tools/export_web_policy.py`(함수 분리, 동작 동일).
- 문서: `jobs/README.md`, `docs/ARCHITECTURE.md`.
## 측정 지표와 측정창
머지 후 `mode=export` 디스패치 3건(M2–M4 run 대상) 또는 14일 중 먼저 오는 쪽. cloud.yml run 로그와 ops 커밋에서 센다.
- 요약 생성률 = 성공한 `mode=export` run 중 `ops:cloud/exports/<run>.json`이 커밋된 비율
- 원장 줄 수 = `mode=export` run이 `ops:budget/ledger.jsonl`에 남긴 줄 수(0이어야 한다)
- 파드 생성 수 = `mode=export` run 로그의 launcher 호출 수(0이어야 한다)
- 오류 메시지 적합성 = 실패한 `mode=export` run의 첫 오류 줄이 원인(아티팩트 없음/만료, 입력 형식, `player_mix` 없음)과 고치는 방법을 말하는 비율
- 기존 모드 회귀 = 측정창 안 `check`·`run`·`reap`·`collect` run 중 이 변경 때문에 실패한 수
## 성공 기준 (수치)
- 요약 생성률 3/3 (100%)
- 원장 줄 0, 파드 생성 0
- 오류 메시지 적합성 100% (실패가 없으면 해당 없음)
- 기존 모드 회귀 0건
## 롤백 방법
PR #590을 revert한다(`export` 케이스·입력 4개·export 스텝 4개·`push_ledger.sh`의 `cloud/exports` 경로가 함께 되돌아간다).
`ops:cloud/exports/` 파일은 남지만 다른 코드가 읽지 않으므로 지울 필요 없다. `export_web_policy --players`(#585)는 revert 뒤에도 로컬에서 그대로 쓸 수 있다.
## 확장 (#596, PR #598, 2026-11-06)
- 변경: 입력 `export_min_visits_by_players`(정규식 검증, 기본 빈 문자열), export 스텝이 `--min-visits-by-players`·`--policies-out ops/cloud/policies/<run>`를 넘김,
  `push_ledger.sh`가 `cloud/policies`도 커밋. 3MB 상한 안 파일과 그 파일만 나열한 `index.json`만 올라간다(`--index-base`의 기존 항목은 유지). 요약 `files[].min_visits` 추가.
- 가설: 에이전트가 ops에서 정책 파일을 직접 읽어 `web/app/policy/` PR을 만들 수 있다(아티팩트 403 우회).
- 추가 지표: 상한 안 파일 수 = `ops:cloud/policies/<run>/`의 `<등급>-<n>.json` 수 = 요약 `within_page_budget=true` 수(100% 일치), `index.json`이 올라간 파일만 나열(위반 0).
  측정창·성공 기준은 위와 같다(다음 export 디스패치 3건 또는 14일).
- 롤백: PR #598 revert. 입력 1개·플래그 2개·`cloud/policies` 경로가 되돌아가고 `ops:cloud/policies/` 파일은 남지만 읽는 코드가 없어 지울 필요 없다.

## 확장 (#815, PR #818, 2026-11-12)
- 변경: 입력 `export_hit_rate_hands`·`export_hit_rate_seeds`(빈 값 또는 양의 정수 검증, 기본 빈 값), 값이 있을 때만 export 스텝이 `--hit-rate-hands`·`--hit-rate-seeds`를 넘김(`extra` 배열). 빈 값이면 명령줄 불변.
- 가설: #805의 hit_rate 재측정을 코드 수정 없이 디스패치 입력만으로 할 수 있다.
- 지표·측정창: hit-rate 입력이 있는 export 디스패치 N건(3건) 또는 14일. (a) 입력이 요약 `files[].hit_rate`에 반영되는 비율 100%, (b) 입력이 빈 기존 디스패치의 회귀 0건.
- 롤백: PR #818 revert. 입력 2개·env 2개·검증 2줄·`extra` 배열이 되돌아간다.

## 결과 (측정창 종료 후 기록)
