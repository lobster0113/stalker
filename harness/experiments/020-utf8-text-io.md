# 020: 텍스트 입출력에 인코딩을 명시해 Windows 로컬 gates quick 통과
- 상태: 진행 중
- 제안: 대화 세션, 2026-10-28 / 이슈 #191 / PR (이 PR)
## 문제 (관측 근거)
Windows 11(cp949)의 대화 세션에서 `python -m referee.gates quick`이 코드와 무관하게 실패한다.
- `read_text`/`write_text`/`open`과 `subprocess(text=True)`가 기본 인코딩 cp949로 UTF-8 파일과 출력을 읽는다(`UnicodeDecodeError`, `test_service` 등).
- 셸 스크립트 가짜 바이너리를 실행하는 테스트 5건이 WinError 193으로 실패한다.
- CI(Linux)는 통과한다. 하지만 `gates quick`이 첫 실패에서 멈추므로 로컬 참고값을 얻을 수 없었다.
## 가설
`harness/`·`stalker/`·`scripts/`·`tests/`의 모든 텍스트 입출력에 `encoding="utf-8"`을 명시하고, POSIX 전용 테스트는 Windows에서 사유를 적어 건너뛰면 `PYTHONUTF8` 없이도 Windows에서 통과한다. Linux 동작은 같다(이미 UTF-8 기본값).
## 변경
- 79곳에 `encoding="utf-8"` 추가: `read_text`/`write_text`/텍스트 `open` 72곳, `subprocess` `text=True` 7곳.
- 검사 테스트 `tests/test_text_encoding.py`: AST로 위 호출에 인코딩이 빠진 곳이 0건임을 단언한다.
- `tests/test_texassolver.py` 4건과 `tests/test_harness.py::test_texassolver_job_cache_key_tracks_install_commit`은 `sys.platform == "win32"`에서 skip한다. Linux CI에서는 그대로 실행된다.
- 런처 회귀 테스트: Windows 상대 경로 허용, 중첩 경로 거부.
## 측정 지표와 측정창
머지 후 7일: Windows 대화 세션에서 `python -m referee.gates quick`(PYTHONUTF8 없이)이 환경 때문에 실패한 횟수, CI 테스트 수(감소 없음).
## 성공 기준
환경 원인 실패 0건, CI 테스트 수 유지.
## 롤백 방법
이 PR을 revert.
## 결과
(측정창 종료 후 auditor가 기록)
