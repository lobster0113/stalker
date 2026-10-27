# 016: gates를 tests·checks 두 병렬 잡으로 분할
- 상태: 진행 중
- 제안: 대화 세션, 2026-10-27 / 이슈 #206 / PR (이 PR)
## 문제 (관측 근거)
- #190(xdist)·#200(상한 50분) 뒤에도 `gates`는 약 30분이다: tests 937s + gate_r 801s(#190 코멘트, CI 러너).
- 리뷰어는 PR마다 CI를 기다린다. 10-27 밤에는 웹훅 실행이 겹쳐 P0 PR(#190, #200)이 약 3시간 판정되지 않았다(#205).
## 가설
테스트 스위트와 등록 검사(gate_r·gate_r_edge·gate_l)는 서로 독립이다. 두 잡으로 병렬로 돌리면 필수 체크 `gates`의 완료 시간이 max(약 16분, 약 15분)로 줄고, 검사 범위는 그대로다.
## 변경
- `referee/gates.py`: `full --part tests|checks`(기본 all = 이전 동작).
- `.github/workflows/ci.yml`: `gates-part` 매트릭스(tests, checks, 각 50분 상한). 필수 체크 이름 `gates`는 집계 잡으로 둔다(`if: always()`, 파트 결과가 success가 아니면 실패). 건너뜀이나 취소된 파트는 통과로 보지 않는다.
- 테스트: 파트 분할이 검사를 빠뜨리지 않음(`tests/test_gates.py`), CI 구조(`tests/test_harness.py`).
## 측정 지표와 측정창
머지 후 7일. (1) PR CI 집계 `gates` 완료까지 걸린 시간 중앙값, (2) CI success부터 리뷰 판정까지 걸린 시간 중앙값, (3) 러너 분(비용 0, 공개 리포지만 동시 실행 수 확인).
## 성공 기준
(1) 20분 이하(기준 약 30분), (2) 악화 없음, (3) 동시 실행 한도에 걸린 대기가 없음.
## 롤백 방법
이 PR을 revert한다. `gates.py`의 기본 동작은 그대로라 다른 호출자에는 영향이 없다.
## 결과
(측정창 종료 후 auditor가 기록)
