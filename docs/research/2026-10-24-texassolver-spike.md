# TexasSolver 클라우드 연동 스파이크 (#8)

- 상태: **측정 완료(#40), 추천: 채택.** 아래 "측정 결과"는 CI 잡 `texassolver` run [40171693446](https://github.com/lobster0113/stalker/actions/runs/40171693446) 수치다. "업스트림 공개 수치"는 TexasSolver 저장소가 공개한 값이다(우리 측정 아님).
- 고정 버전: `console` 브랜치 `6dfb65b4d7ed081da509e8d8c3d82138c4708267` (2026-08-19). 릴리스 v0.2.0은 GUI 빌드라 헤드리스 Linux에 맞지 않는다.
- 라이선스: AGPL-3.0, 개인 연구용(ADR 0002 결정 3). 바이너리와 소스는 리포에 넣지 않고 설치 스크립트로만 받는다.

## 구성
| 파일 | 역할 |
|---|---|
| `scripts/install_texassolver.sh` | 고정 커밋을 shallow fetch → `CMakeLists.txt`에서 `add_subdirectory(ext/pybind11)` 제거(콘솔 빌드에 불필요하고, 동봉된 pybind11 2.2가 Python 3.12에서 없어진 `distutils`를 import해 configure가 실패함 — run 40171427531) → cmake Release 빌드(`console_solver` 타깃만) → `$STALKER_TEXASSOLVER_HOME`(기본 `~/.cache/stalker/texassolver`)에 바이너리·`resources/`·`VERSION` 설치. 도구 부재·OpenMP 부재·네트워크·cmake·빌드 실패를 각각 원인과 함께 출력. 같은 커밋이 설치돼 있으면 건너뜀. 의존성: git, cmake ≥3.15, g++(C++17, OpenMP). 서드파티(fmt·googletest·pybind11)는 소스 트리에 포함되어 있어 서브모듈이 필요 없다. |
| `stalker/oracle/texassolver.py` | `Spot`(보드·팟·유효 스택·레인지·`(player, street)`별 벳사이즈) → 명령 파일 → `console_solver -i` 실행(임시 디렉터리, `os.wait4`로 프로세스 피크 RSS) → `dump_result` JSON → `RootStrategy`(행동 주체, 액션 문자열, `(hi, lo)` 콤보별 확률). `parse_root(dump, path)`로 같은 스트리트의 하위 노드도 읽는다. 솔버 로그(`tmp_log.txt`)에서 마지막 exploitability·반복 수. |
| `stalker/tools/bench_texassolver.py` | 같은 레인지·한 벳사이즈(66% 벳, 100% 레이즈, 올인) 트리로 리버/턴/플랍 × 목표 정확도(1, 0.5, 0.3 %pot) 솔브 → JSON 줄(시간·RSS·exploitability·반복·하루 스팟 수). |
| `tests/test_texassolver.py` | 바이너리 없이: 입력 생성·검증, 덤프 파싱(가짜 덤프), 로그 파싱, 가짜 실행 파일로 `solve` 배관·실패·타임아웃. 바이너리 있으면(`slow`): 리버 스팟 확률합=1, 넛(KK, Ks Td 7h 3c 2s)은 벳에 직면해 폴드 < 1%. |

## 솔버 규약 (고정 커밋 소스 `src/tools/CommandLineTool.cpp`, `src/solver/PCfrSolver.cpp`에서 확인)
- 명령은 공백으로 나뉘며 인자는 하나뿐 → 레인지 문자열에 공백이 있으면 안 된다(래퍼가 제거).
- `set_pot P`는 양쪽 커밋을 P/2로 둔다. `set_effective_stack S`는 남은 스택.
- 벳사이즈는 팟 대비 %. `set_accuracy`는 목표 exploitability(%pot). `print_interval`마다만 수렴을 검사하므로 실제 종료 반복은 그 배수+1.
- 덤프의 `player` 1 = OOP, 0 = IP. 루트는 해당 스트리트 OOP 첫 결정. 보드와 겹치는 콤보는 솔버가 제거한다. 액션 문자열은 `CHECK`, `FOLD`, `CALL`, `BET 50.000000`, `RAISE 200.000000` 형식(C++ `to_string`).
- 덤프 깊이 `set_dump_rounds 1` = 현재 스트리트만. 다음 스트리트(찬스 노드 이후)가 필요하면 깊이를 올리거나 해당 보드로 다시 솔브.

## 측정 결과 (CI)
- 출처: 워크플로 `texassolver` run [40171693446](https://github.com/lobster0113/stalker/actions/runs/40171693446) (2026-10-25, 브랜치 `claude/40-texassolver-bench` 커밋 `f82f0d8`, 기본 입력 river turn flop × 1 0.5 0.3), 아티팩트 `texassolver-bench-40171693446`. 같은 줄이 잡 로그 bench 스텝에도 찍힌다. 로컬 수치는 쓰지 않았다.
- main(`a3c9362`)에서 처음 돌린 run 40171427531은 설치 단계 cmake configure에서 실패했다(pybind11 → `distutils`, 위 "구성" 참고). 설치 스크립트를 고친 브랜치로 다시 dispatch했다.
- 러너: GitHub `ubuntu-latest`, Python 3.12.15, 솔버 4스레드(`os.cpu_count()`). 솔버 커밋 `6dfb65b4`. 같은 잡의 slow 테스트(리버 확률합·넛 폴드) 통과.
- 트리: `bench_texassolver` 고정 스팟(팟 10, 유효 스택 95, 스트리트별 66% 벳·100% 레이즈·올인 한 가지씩, README 공개 레인지). 실전 트리(사이즈 2~3개)는 이보다 크다.

| 스트리트 | 목표 %pot | 도달 %pot | 반복 | 시간(s) | 피크 RSS(MB) | 스팟/일(1러너) |
|---|---|---|---|---|---|---|
| river | 1 | 0.94 | 81 | 2.79 | 107.9 | 30,919 |
| river | 0.5 | 0.44 | 121 | 2.86 | 108.0 | 30,223 |
| river | 0.3 | 0.30 | 151 | 2.63 | 107.9 | 32,895 |
| turn | 1 | 0.93 | 81 | 3.41 | 121.2 | 25,325 |
| turn | 0.5 | 0.49 | 111 | 3.67 | 121.4 | 23,522 |
| turn | 0.3 | 0.28 | 161 | 4.05 | 121.4 | 21,356 |
| flop | 1 | 0.81 | 91 | 70.26 | 767.9 | 1,230 |
| flop | 0.5 | 0.45 | 121 | 91.42 | 768.0 | 945 |
| flop | 0.3 | 0.27 | 161 | 126.14 | 768.0 | 685 |

해석:
- 리버·턴은 정확도와 거의 무관하게 3~4초, RSS ~110MB다. 리버에서 반복 수가 2배 가까이 늘어도 시간이 그대로이므로, 이 시간 대부분은 솔브가 아니라 프로세스 시작 시 고정 비용(핸드 평가 테이블 로딩으로 추정, ~2.5초·~100MB)이다. 한 프로세스에서 여러 스팟을 연속으로 푸는 배치 모드를 쓰면 리버·턴 처리량은 이보다 훨씬 높아질 수 있다(추정, 미측정).
- 플랍은 반복 수에 비례해 70~126초, RSS 768MB. 4코어·16GB급 러너 1대로 0.5%면 하루 약 950 스팟, 0.3%면 약 690 스팟.
- 업스트림 공개 벤치(6스레드, 사이즈가 더 많은 트리, 0.3%에 175초)와 크기 차수가 맞는다.

## 결론: 채택
- **판정: 채택.** 헤드리스 Linux에서 고정 커밋으로 소스 빌드(캐시 미스 때 ~35초, 이후 `actions/cache`)·실행·결과 파싱까지 프로그램으로 동작하고, 상식 검증(넛은 폴드 < 1%)을 통과했다. 처리량은 연구용 스팟 라이브러리에 충분하다: 무료 CI 러너 1대로 하루 플랍 ~950 스팟(0.5%) 또는 턴·리버 2만+ 스팟.
- 근거 요약: (1) 실패 없이 9개 조합 전부 목표 정확도 도달, (2) 메모리 768MB로 표준 러너에서 여유, (3) 외부 비용 0(GitHub 호스티드 러너, workflow_dispatch).
- 한계: 한 가지 벳사이즈 트리라 실전 트리는 2~5배 느릴 수 있다. ICM 미반영(칩EV). AGPL이라 바이너리·출력의 외부 배포 금지(개인 연구용, ADR 0002).
- **다음 이슈 제안 — 전략 라이브러리 v0**: (a) 스팟 정의 목록(SRP/3벳팟 × 대표 플랍 묶음 × 유효 스택 버킷)을 데이터 파일로 고정, (b) `workflow_dispatch` 잡이 목록을 나눠 풀고 `RootStrategy`를 JSONL 아티팩트로 저장(솔버 버전·트리·정확도 기록, ADR 0002 "모든 오라클 출력에 기록" 항목), (c) 한 프로세스 배치 솔브로 고정 비용 제거 여부를 측정, (d) 작은 범위(예: 플랍 50스팟 × 0.5%)로 시작해 1러너 1시간 안에 끝나는지 확인.

### CI로 측정하기 (`.github/workflows/texassolver.yml`, #39)
수동 실행 전용(`workflow_dispatch`), PR·push로는 돌지 않고 secret을 쓰지 않는다. 타임아웃 60분.
```bash
gh workflow run texassolver.yml --ref main                                   # 기본: river turn flop × 1 0.5 0.3
gh workflow run texassolver.yml --ref main -f streets="river turn" -f accuracy="0.5"
```
MCP: `actions_run_trigger`(method `run_workflow`, `workflow_id: texassolver.yml`, `ref: main`, 필요하면 `inputs: {streets, accuracy}`).
잡 순서: 설치(`actions/cache`, 키 = 설치 스크립트 `COMMIT`) → 바이너리 존재 확인(slow 테스트가 조용히 skip되지 않게) → `pytest -m slow tests/test_texassolver.py` → 러너 사양 → `bench_texassolver`.
결과는 아티팩트 `texassolver-bench-<run_id>`의 `texassolver-bench.jsonl`: 첫 줄 `{"runner": {os, cpu_model, cpus, mem_mb, python, solver_version, git_sha}}`, 이후 솔브마다 한 줄(`OUTPUT_FIELDS`). 솔브 한 건은 1200초에서 끊긴다(`TexasSolverError`로 벤치 종료). 그때나 잡이 60분 제한에 걸리면 아티팩트에는 그 앞의 줄만 남으므로, 줄 수를 확인하고 빠진 조합은 `streets`/`accuracy` 입력으로 나눠 다시 돌린다.

로컬 재현 명령(수치는 참고용):
```bash
scripts/install_texassolver.sh
python -m stalker.tools.bench_texassolver           # JSON 줄 출력(필드: 모듈 문서 `OUTPUT_FIELDS`)
python -m pytest -m slow tests/test_texassolver.py  # 리버 상식 검증
```

## 업스트림 공개 수치 (참고, 우리 측정 아님)
TexasSolver README의 플랍 벤치(`benchmark/benchmark_texassolver.txt`: Qs Jh 2h, 팟 10, 스택 95, 스트리트별 100% 벳·50% 레이즈·올인, 6스레드, v0.1.0): 메모리 1600MB, 0.275% 도달 172초. 같은 로그에서 목표별 도달 시간:

| 목표 %pot | 반복 | 시간 |
|---|---|---|
| 5 | 51 | 55 s |
| 2 | 61 | 66 s |
| 1 | 91 | 99 s |
| 0.5 | 121 | 132 s |
| 0.3 | 161 | 175 s |

이 수치로 본 처리량 추정(6스레드 1대, 플랍 풀트리): 0.5%면 하루 약 650 스팟, 0.3%면 약 490 스팟. 턴·리버는 트리가 훨씬 작아 수십~수백 배 빠를 것으로 예상하지만 측정 전까지는 가정이다.

## 다음 단계
1. ~~`texassolver` 워크플로를 실행해 위 표를 CI 수치로 채운다(#8-C).~~ 완료(#40, run 40171693446).
2. 결과로 ADR 0003의 참조 봇 v2·RL 교사용 스팟 라이브러리 예산(스팟 수 × 시간)을 잡는다.
