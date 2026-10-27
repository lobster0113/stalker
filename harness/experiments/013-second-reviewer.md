# 013: 두 번째 리뷰어 (reviewer-b), PR 번호 홀짝 분담
- 상태: 진행 중
- 제안: 사용자 요청(대화 세션, 2026-10-27) / 이슈 #175 / PR (이 PR)
## 문제
리뷰어는 role 잠금 때문에 한 번에 하나만 돈다. 실행 중에 들어온 PR 이벤트 실행은 SKIP되고 다시 시도되지 않는다. 그래서 다음 매시 스윕까지 기다린다. 10-27 12~14Z에 열린 PR이 7개였는데 시간당 판정은 1~2건이었다. 수정을 반영한 PR들이 1시간 넘게 재판정을 기다렸다.
## 가설
같은 지침·기준의 리뷰어를 하나 더 두고 PR 번호로 나누면(홀수 `reviewer`, 짝수 `reviewer-b`) 처리량이 두 배가 된다. 같은 PR을 두 리뷰어가 판정하는 일도 생기지 않는다.
## 변경
- 루틴 `stalker-reviewer-b`(trig_01UMyEMLMmpXiHkRqRXp6zUy, opus-5.5, Bash/Read/Glob/Grep, 커넥터 없음, 매시 :10 + PR opened/synchronize/reopened 웹훅). 대화 세션에서 생성.
- `harness/schedule.json`: `reviewer-b`(reviewer와 같은 설정, 잠금은 role별).
- `harness/routines/reviewer.md` §0: 홀짝 분담, 내 몫이 아니면 `skipped` 후 잠금 해제.
- `harness/ROUTINES.md` 표.
## 측정 지표와 측정창
머지 후 7일. (1) 커밋 푸시 → 판정까지 대기 시간(중앙값), (2) 시간당 판정 수, (3) 같은 sha에 대한 중복 판정 수, (4) 두 리뷰어의 CHANGES 비율 차이(기준이 다르게 적용되는지).
## 성공 기준
(1) 기준 대비 절반 이하, (2) 두 배 가까이, (3) 0건, (4) 차이 ≤ 15%p.
## 롤백 방법
schedule.json에서 `reviewer-b`를 `enabled: false`로 두고 reviewer.md 분담 문단을 되돌린다(홀수만 보던 reviewer가 다시 전부 본다). 루틴은 대화 세션이 끈다.
## 결과
(측정창 종료 후 auditor가 기록)
