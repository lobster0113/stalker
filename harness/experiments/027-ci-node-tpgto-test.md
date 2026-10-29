# 027: CI web 잡에서 JS TP-GTO 엔진 node 테스트 실행
- 상태: 진행 중
- 제안: 대화 세션, 2026-10-30 / 이슈 #349 / PR (이 PR)
## 문제 (관측 근거)
- `web/app/test/tpgto.test.mjs`(#335, PR #342)는 `web/app/tpgto.js`가 Python 학습기와 키·레인지·payoff가 정확히 같은지 검사한다. 지금은 `tests/test_web_vectors.py`가 node가 있을 때만 돌리고, CI `gates` 잡에는 node가 없어 skip된다.
- 서비스 화면은 이 엔진으로 학습된 정책을 찾는다(#337, #360). 어긋나면 정책 키를 못 찾고 균등 분포로 떨어지는데, CI가 이를 잡지 못한다.
## 가설
node가 이미 설치되는 `web` 잡에 node 테스트 한 단계를 넣으면 JS·Python 불일치가 PR CI에서 실패로 드러난다. 추가 시간은 몇 초다.
## 변경
`.github/workflows/ci.yml` `web` 잡: `npm ci` 앞에 `node --test web/app/test/tpgto.test.mjs`.
## 측정 지표와 측정창
머지 후 14일. 근거는 CI web 잡 로그.
- web 잡 로그의 node 테스트 통과 수(현재 8개)와 단계 소요 시간.
- 이 단계 때문에 실패한 PR과 그 원인(실제 불일치인지, 환경 문제인지).
## 성공 기준 (수치)
- 이 PR의 web 잡 로그에 `ℹ pass 8`, `ℹ fail 0` (node 22+ spec reporter).
- 측정창 안 web 잡 시간 증가 중앙값 ≤ 30초.
- 환경 문제로 인한 이 단계의 거짓 실패 0건.
## 롤백 방법
이 PR을 revert한다. 검사는 node가 있는 로컬 `tests/test_web_vectors.py`로 돌아간다.
## 결과 (측정창 종료 후 기록)
