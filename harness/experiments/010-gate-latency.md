# 010: 게이트 진행 출력과 quick 게이트 90초
- 상태: 진행 중
- 제안: planner(friction a), 이슈 #104 / PR (이 PR). 구현: 대화 세션(2026-10-27)
## 문제
`gates quick/full`이 성공하면 아무것도 출력하지 않은 채 몇 분~몇십 분 걸려, 루틴의 포그라운드 명령 타임아웃(120초)과 reviewer의 20분 대기를 자주 넘었다(10-26에만 8회 이상, `ops:STATE.md` friction a). 로컬 측정(Windows, 참고값): `-m "not slow"` 약 275초, 그중 `test_director` mtt180 한 건이 109초.
## 가설
(1) 단계마다 진행 줄을 내고 full을 백그라운드로 돌리게 하면 타임아웃으로 끊기는 실행이 사라진다. (2) quick에서 몇 초 이상인 테스트를 `slow`로 옮기면 quick이 90초 안에 든다. full은 같은 테스트를 그대로 돌리므로 검증 범위는 줄지 않는다.
## 변경
- `referee/gates.py`: 단계마다 stderr에 `[gate] <단계> ...`, `[gate] <단계> ok|FAIL <초>`, stdout 요약에 단계별 시간.
- quick에서 `slow`로 옮김(삭제 없음): `test_director` mtt180·mtt54 매개변수, `test_gate_r` mtt54, `test_rl_env` 100토너먼트, `test_gate_stats` 2건, 은퇴 지표 모듈 테스트(`test_gate_b`·`test_gate_b_pilot`·`test_gate_a_spots`·`test_sufficiency`·`test_sufficiency_curve`).
- 로컬 결과(참고값): quick 테스트 275초 → 77초.
- `harness/routines/builder.md`·`reviewer.md`: full과 CI 대기는 백그라운드 + 완료 대기.
## 측정 지표와 측정창
머지 후 14일. (1) journal `friction`에서 게이트·CI 대기 타임아웃 언급 건수, (2) CI `gates` 잡 소요 시간(분, 중앙값), (3) builder 실행당 quick 소요(진행 줄의 초).
## 성공 기준
(1) 기준(10-26 하루 8회+) 대비 주 2회 이하, (2) 악화 없음(full은 그대로라 같아야 정상), (3) 중앙값 ≤ 90초.
## 롤백 방법
이 PR을 revert. 진행 출력은 stderr라 다른 도구에 영향 없음.
## 결과
(측정창 종료 후 auditor가 기록)
