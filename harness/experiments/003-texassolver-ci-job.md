# 003: TexasSolver 빌드·측정 workflow_dispatch 잡
- 상태: 진행 중
- 제안: planner, 2026-10-24 / 이슈 #39 / PR #58

## 문제 (관측 근거: journal·지표·리포트 인용)
TexasSolver 처리량 수치(#8-C, #40)를 낼 곳이 없다. builder 실행 환경은 외부 코드 빌드·실행을 거부하고, 성능 수치의 근거는 CI뿐이다.
- #8 인수인계: "builder 실행 환경이 외부 코드 빌드·실행을 허용하지 않아 바이너리를 돌리지 못했다" (`docs/research/2026-10-24-texassolver-spike.md` 상태 줄).
- 스파이크 문서 "측정 결과" 표가 비어 있고, #40이 이 잡을 기다리며 blocked.

## 가설
수동 실행 전용 잡(`workflow_dispatch`)이 설치(커밋 키 캐시) → slow 테스트 → 벤치를 돌려 러너 사양과 솔브별 JSON 줄을 아티팩트로 남기면, #40이 로컬 실행 없이 CI 수치만으로 표를 채울 수 있다. PR·push 트리거가 없으므로 필수 체크와 CI 시간에는 영향이 없다.

## 변경
- `.github/workflows/texassolver.yml`: `workflow_dispatch`(입력 `streets`·`accuracy`), 60분 제한, `permissions: contents: read`, secret 없음. `actions/cache` 키 = 설치 스크립트 `COMMIT`. 바이너리 존재 assert(slow 테스트 skip 방지), 솔브당 `--timeout 1200`, `upload-artifact`(`if: always()`).
- `tests/test_harness.py`: 트리거·제한·캐시 키·단계 순서·secret 부재·입력 주입 방지를 검사하는 테스트 2개.
- 문서: 스파이크 문서 "CI로 측정하기", `docs/ARCHITECTURE.md` CI 항목.

## 측정 지표와 측정창 (머지 후 14일)
1. 머지 후 첫 dispatch(기본 입력)가 잡 timeout 없이 success로 끝나는가.
2. 그 run의 아티팩트에 러너 줄 1개 + 솔브 줄(기본 입력이면 9개)이 있는가.
3. 캐시 적중 run의 install 단계 시간(목표: 캐시 미스 run 대비 1/10 이하).
4. #40이 로컬 수치 없이 CI 아티팩트만으로 표를 채웠는가(journal·PR 본문).

## 성공 기준 (수치)
- 지표 1·2: 첫 기본 입력 run에서 충족(실패 시 입력을 나눈 run 1회까지 허용).
- 지표 3: 캐시 적중 run의 install ≤ 10s.
- 지표 4: 예.

## 롤백 방법
`.github/workflows/texassolver.yml`과 `tests/test_harness.py`의 `test_texassolver_job_*` 2개를 지우는 PR 하나(`harness-change`). 필수 체크가 아니므로 다른 잡·코드에 영향 없음.

## 결과 (측정창 종료 후 기록)
(미기록)
