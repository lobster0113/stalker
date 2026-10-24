# TexasSolver 클라우드 연동 스파이크 (#8)

- 상태: **연동 코드 완료, 측정 미완료.** builder 실행 환경이 외부 코드 빌드·실행을 허용하지 않아 바이너리를 돌리지 못했다. 아래 "측정 결과"는 비어 있고, "업스트림 공개 수치"는 TexasSolver 저장소가 공개한 값이다(우리 측정 아님).
- 고정 버전: `console` 브랜치 `6dfb65b4d7ed081da509e8d8c3d82138c4708267` (2026-08-19). 릴리스 v0.2.0은 GUI 빌드라 헤드리스 Linux에 맞지 않는다.
- 라이선스: AGPL-3.0, 개인 연구용(ADR 0002 결정 3). 바이너리와 소스는 리포에 넣지 않고 설치 스크립트로만 받는다.

## 구성
| 파일 | 역할 |
|---|---|
| `scripts/install_texassolver.sh` | 고정 커밋을 shallow fetch → cmake Release 빌드(`console_solver` 타깃만) → `$STALKER_TEXASSOLVER_HOME`(기본 `~/.cache/stalker/texassolver`)에 바이너리·`resources/`·`VERSION` 설치. 도구 부재·OpenMP 부재·네트워크·cmake·빌드 실패를 각각 원인과 함께 출력. 같은 커밋이 설치돼 있으면 건너뜀. 의존성: git, cmake ≥3.15, g++(C++17, OpenMP). 서드파티(fmt·googletest·pybind11)는 소스 트리에 포함되어 있어 서브모듈이 필요 없다. |
| `stalker/oracle/texassolver.py` | `Spot`(보드·팟·유효 스택·레인지·`(player, street)`별 벳사이즈) → 명령 파일 → `console_solver -i` 실행(임시 디렉터리, `os.wait4`로 프로세스 피크 RSS) → `dump_result` JSON → `RootStrategy`(행동 주체, 액션 문자열, `(hi, lo)` 콤보별 확률). `parse_root(dump, path)`로 같은 스트리트의 하위 노드도 읽는다. 솔버 로그(`tmp_log.txt`)에서 마지막 exploitability·반복 수. |
| `stalker/tools/bench_texassolver.py` | 같은 레인지·한 벳사이즈(66% 벳, 100% 레이즈, 올인) 트리로 리버/턴/플랍 × 목표 정확도(1, 0.5, 0.3 %pot) 솔브 → JSON 줄(시간·RSS·exploitability·반복·하루 스팟 수). |
| `tests/test_texassolver.py` | 바이너리 없이: 입력 생성·검증, 덤프 파싱(가짜 덤프), 로그 파싱, 가짜 실행 파일로 `solve` 배관·실패·타임아웃. 바이너리 있으면(`slow`): 리버 스팟 확률합=1, 넛(KK, Ks Td 7h 3c 2s)은 벳에 직면해 폴드 < 1%. |

## 솔버 규약 (고정 커밋 소스 `src/tools/CommandLineTool.cpp`, `src/solver/PCfrSolver.cpp`에서 확인)
- 명령은 공백으로 나뉘며 인자는 하나뿐 → 레인지 문자열에 공백이 있으면 안 된다(래퍼가 제거).
- `set_pot P`는 양쪽 커밋을 P/2로 둔다. `set_effective_stack S`는 남은 스택.
- 벳사이즈는 팟 대비 %. `set_accuracy`는 목표 exploitability(%pot). `print_interval`마다만 수렴을 검사하므로 실제 종료 반복은 그 배수+1.
- 덤프의 `player` 1 = OOP, 0 = IP. 루트는 해당 스트리트 OOP 첫 결정. 보드와 겹치는 콤보는 솔버가 제거한다. 액션 문자열은 `CHECK`, `FOLD`, `CALL`, `BET 50.000000`, `RAISE 200.000000` 형식(C++ `to_string`).
- 덤프 깊이 `set_dump_rounds 1` = 현재 스트리트만. 다음 스트리트(찬스 노드 이후)가 필요하면 깊이를 올리거나 해당 보드로 다시 솔브.

## 측정 결과 (이 환경)
측정하지 못했다. 재현 명령:
```bash
scripts/install_texassolver.sh
python -m stalker.tools.bench_texassolver           # JSON 줄 출력
python -m pytest -m slow tests/test_texassolver.py  # 리버 상식 검증
```
| 스트리트 | 목표 %pot | 시간 | 피크 RSS | 반복 | 스팟/일 |
|---|---|---|---|---|---|
| river | 1 / 0.5 / 0.3 | – | – | – | – |
| turn | 1 / 0.5 / 0.3 | – | – | – | – |
| flop | 1 / 0.5 / 0.3 | – | – | – | – |

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
1. 외부 코드 빌드가 허용된 곳(CI의 별도 `workflow_dispatch`/slow 잡, 또는 허용된 실행 환경)에서 설치 + `bench_texassolver` + `pytest -m slow` 실행, 위 표를 CI 수치로 채운다. 이 잡은 `.github/` 수정이라 `harness-change` 이슈가 필요하다.
2. 결과로 ADR 0003의 참조 봇 v2·RL 교사용 스팟 라이브러리 예산(스팟 수 × 시간)을 잡는다.
