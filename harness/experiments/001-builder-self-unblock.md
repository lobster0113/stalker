# 001: builder 자가 언블록
- 상태: 진행 중
- 제안: auditor, 2026-10-25 / 이슈 #55 / PR #57
## 문제
builder 실행의 24%(41회 중 10회)가 no_work였다. planner는 실제로 하루 1회(21:00 UTC)만 돌아서, 선행이 닫힌 blocked 이슈가 최대 24시간 동안 ready로 바뀌지 않는다(#13·#15·#17 사례).
## 가설
선행 대기만이 사유인 blocked 이슈를 builder가 직접 ready로 바꾸게 하면, builder no_work 비율이 10% 이하로 떨어지고 머지 처리량은 유지된다.
## 변경
builder.md 이슈 선택 단계에 자가 언블록 규칙 추가. ROUTINES.md planner 주기 표기 정정.
## 측정 지표와 측정창
머지 후 14일. (1) builder·builder-b journal의 no_work 비율, (2) 일 평균 머지 수, (3) 언블록된 이슈가 나중에 needs-split/CLOSE가 된 비율(잘못된 언블록 여부).
## 성공 기준
no_work 비율 ≤ 10%, 일 평균 머지 수가 직전 주의 80% 이상, 잘못된 언블록 0~1건.
## 롤백 방법
builder.md의 자가 언블록 문단을 되돌리는 PR(ROUTINES.md 정정은 유지).
## 결과
(측정창 종료 후 auditor가 기록)
