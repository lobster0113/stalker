# 030: MERGE 판정 뒤 머지가 실패한 PR의 머지 재시도
- 상태: 진행 중
- 제안: auditor, 2026-11-01 / 이슈 #482 / PR (이 PR)
## 문제 (관측 근거)
- #466: 10-31 01:56Z에 MERGE 판정, 01:57Z에 squash 머지가 세션 권한 분류기에 거부됨. 이후 22시간 넘게 열려 있음. #480: 18:19Z에 같은 상태.
- reviewer.md §2의 같은 sha 규칙 때문에 이후 스윕은 모두 skipped/no_work. 10-31 journal에 이 friction이 20회 이상, builder-b no_work 2회(슬롯 점유).
- 그 결과 #373·#462는 닫히지 않고, #401은 막혀 있다.
## 가설
같은 sha에 MERGE 판정이 있고, 필수 체크가 success이며, 충돌이 없는 열린 PR에 대해 "재판정 없이 머지만 재시도"(PR당 최대 3회)와 "초과 시 NEEDS_HUMAN에 한 번 등록"을 두면, 판정을 받고도 열려 있는 PR이 3시간 안에 머지되거나 사람에게 넘어간다.
## 변경
reviewer.md 규칙, `MERGE-RETRY failed <UTC> <이유>` 코멘트 카운트, should_run 작업 판정(`merge_retry_candidates`), 테스트.
## 측정 지표와 측정창 (머지 후 7일)
(1) MERGE 판정 뒤 3시간 넘게 열려 있고 NEEDS_HUMAN 항목도 없는 PR 수, (2) journal에서 같은 sha 정체 friction 수, (3) 재시도 성공률.
## 성공 기준 (수치)
(1) 0건, (2) 3건 이하(기준선: 10-31 하루 20건 이상), (3) 재시도 대상 PR 중 머지됐거나 NH에 등록된 비율 100%.
## 롤백 방법
이 PR을 revert한다.
## 결과 (측정창 종료 후 기록)
