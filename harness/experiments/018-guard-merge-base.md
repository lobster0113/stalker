# 018: guard의 비교 기준을 현재 main과의 merge-base로
- 상태: 진행 중
- 제안: 대화 세션, 2026-10-27 / 이슈 #219 / PR (이 PR)
## 문제 (관측 근거)
10-27 밤 #135·#136·#139·#180·#193·#212의 `guard`가 PR이 바꾸지 않은 하네스 파일 때문에 실패했다. 리뷰어 journal에 "guard false positive / stale base.sha race"가 반복된다. 매번 main을 다시 병합하고 CI를 처음부터 돌려야 했다(약 17–30분 지연).
## 가설
이벤트의 `pull_request.base.sha`가 PR이 이미 병합한 main보다 오래되면 3점 diff에 main 커밋이 섞인다. CI에서 base 브랜치를 새로 가져와 `git merge-base origin/<base_ref> HEAD`를 기준으로 쓰면 PR 자신의 변경만 남는다.
## 변경
`.github/workflows/ci.yml` guard 단계: `base_ref`를 env로 받아 fetch하고 merge-base를 `--base`로 넘긴다. `referee/guard.py`는 그대로다.
## 측정 지표와 측정창
머지 후 7일: guard 실패 중 PR이 바꾸지 않은 파일이 원인인 건수(리뷰 코멘트·journal).
## 성공 기준
0건.
## 롤백 방법
이 PR을 revert.
## 결과
(측정창 종료 후 auditor가 기록)
