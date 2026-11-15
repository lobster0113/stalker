# 039: 라벨 이벤트는 guard만 다시 돌린다
- 상태: 진행 중
- 제안: auditor, 2026-11-15 / 이슈 #889
## 문제 (관측 근거)
- W46(11-08~11-14)에 머지 PR 121건 중 83건(69%)에서 같은 head sha에 취소된 이전 run의 `gates` failure가 남았다(위반은 아니지만 매 판정마다 수동 판별 필요). journal friction 458건 중 취소/stale 관련이 90건. 라벨 이벤트가 진행 중인 run을 취소해 CI를 처음부터 다시 돌리므로 PR마다 gates(tests) 약 40분이 늘고 리뷰어의 40분 대기 한도를 넘는 경우가 생긴다(`waiting_ci` 11건). 근거: `ops:reports/2026-W46.md` §1·§3.
## 가설
라벨 이벤트가 `ci.yml`을 다시 시작하는 것이 잔재와 지연의 주원인이다. 이벤트를 분리하면 잔재와 friction이 사라지고 PR 리드타임 중앙값이 줄어든다.
## 변경
- `ci.yml` `pull_request.types`에서 `labeled`·`unlabeled` 제거.
- 새 `guard-labels.yml`: 라벨 이벤트에서만 `guard` 잡(같은 명령, 별도 concurrency 그룹, `gates` 잡 없음).
- `tests/test_harness.py::test_label_events_rerun_only_guard`, `reviewer.md` 한 줄.
## 측정 지표와 측정창
머지 후 7일. (1) 머지 PR 중 head sha에 취소 run의 gates failure가 남은 비율(기준선 69%). (2) journal friction 취소/stale 키워드 건수(기준선 90/주). (3) PR 리드타임 중앙값(기준선 43분). (4) 리뷰어 `waiting_ci` 건수(기준선 11/주).
## 성공 기준 (수치)
(1) ≤ 10%, (2) ≤ 10건, (3) 악화 없음(≤ 43분). 라벨 변경만으로 guard가 고쳐지는 PR이 머지 가능 상태가 되지 못한 사례 0건.
## 롤백 방법
이 PR을 revert한다.
## 결과 (측정창 종료 후 기록)
