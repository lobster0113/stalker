# 019: 클라우드 런처의 잡 명세 경로를 OS와 무관하게 POSIX로 비교
- 상태: 진행 중
- 제안: 대화 세션, 2026-10-28 / 이슈 #225 / PR (이 PR)
## 문제 (관측 근거)
Windows 로컬에서 `tests/test_cloud_launcher.py` 6개가 실패한다. `load_spec`이 `str(rel)`(`jobs\smoke-cpu.yaml`)을 `jobs/[^/]+\.yaml`과 비교해서, 체크인된 명세도 거부한다. CI(Linux)는 영향이 없다. 하지만 로컬 `gates quick`이 첫 실패에서 멈추므로, Windows에서 일하는 세션은 다른 실패를 볼 수 없다.
## 가설
상대 경로를 `as_posix()`로 비교하면 Linux 동작은 그대로이고 Windows에서도 같은 판정이 나온다. 명세는 UTF-8로 읽는다(cp949 기본값 회피).
## 변경
`harness/cloud/launcher.py`: `_rel_posix(path, root)` 도입. `load_spec`이 그 결과로 검사하고 `parse_spec`에 이름을 넘긴다. `read_text(encoding="utf-8")`. 테스트 `test_spec_names_use_forward_slashes_on_windows_paths`(PureWindowsPath).
## 측정 지표와 측정창
머지 후 7일: Windows 로컬 세션의 `tests/test_cloud_launcher.py` 실패 수(대화 세션 기록), CI의 같은 테스트 결과.
## 성공 기준
Windows 0건 실패, CI 계속 통과.
## 롤백 방법
이 PR을 revert.
## 결과
(측정창 종료 후 auditor가 기록)
