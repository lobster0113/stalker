# 010: 워크플로 YAML 유효성 검사를 G0에 넣는다
- 상태: 진행 중
- 제안: planner, 2026-10-26 / 이슈 #126 / PR (이 브랜치 `claude/126-cloud-yml-parse`)

## 문제 (관측 근거: journal·지표·리포트 인용)
#125(머지 8736dbd)의 `.github/workflows/cloud.yml` 75행 `run:` 값이 따옴표 없는 스칼라 안에 `: `를 담고 있어
YAML 파싱이 실패했다. main push run 40387708043은 잡 0개 `failure`로 끝났고, 예산 가드 런처의 `workflow_dispatch`와
매일 03:17 고아 파드 정리도 실행될 수 없었다. Reviewer는 CI 결과(gates·guard·rl green)로 판정했지만 그 CI는 `ci.yml`이라
`cloud.yml`의 파싱 실패를 보지 못했다. planner journal(2026-10-26T21:30Z): "CI 실패 run(잡 0개 YAML 오류)은 conclusion만 failure라 health 점검에서 놓치기 쉬움".

## 가설
모든 `.github/workflows/*.yml`을 `yaml.safe_load`로 읽고 `on`·비어 있지 않은 `jobs`를 확인하는 테스트를 G0 quick에 두면,
같은 종류의 실수는 PR CI(`gates` 잡)에서 머지 전에 잡힌다.

## 변경
- `tests/test_harness.py::test_every_workflow_is_valid_yaml_with_triggers_and_jobs` 추가 (G0 quick에 포함).
- `cloud.yml` 75행 `run:` 값을 작은따옴표로 감쌈.
- `pyproject.toml` `[dev]`에 `pyyaml>=6`.

## 측정 지표와 측정창 (머지 후 14일)
- main push에서 잡 0개로 끝난(워크플로 파싱 실패) Actions run 수.
- 위 테스트가 PR CI에서 실패를 낸 횟수(잡아낸 사례).

## 성공 기준 (수치)
- 측정창 동안 main의 워크플로 파싱 실패 run 0건.
- 이 검사로 인한 오탐(유효한 워크플로가 실패) 0건.

## 롤백 방법
테스트 함수를 지우고 `pyproject.toml`의 `pyyaml` 항목을 뺀다(`cloud.yml` 따옴표 수정은 유지).

## 결과 (측정창 종료 후 기록)
