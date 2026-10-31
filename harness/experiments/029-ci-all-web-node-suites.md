# 029: CI web 잡에서 모든 web node 테스트 실행, CI에서 node 없으면 실패
- 상태: 진행 중
- 제안: 대화 세션, 2026-10-31 / 이슈 #436 / PR (이 PR)
## 문제 (관측 근거)
- CI `web` 잡은 `web/app/test/tpgto.test.mjs`만 돌린다(실험 027). `tells.test.mjs`(#433), `personas.test.mjs`(#434·#435), `leaks.test.mjs`(#450)는 pytest 래퍼(`tests/test_web_*.py`)로만 돌고, 래퍼는 node가 없으면 skip한다. PR #433·#434·#435 본문이 "needs a harness-change issue"로 남겼다.
- skip은 CI에서 초록으로 보이므로, 러너 이미지에서 node가 빠지면 세 스위트가 조용히 검사에서 빠진다.
## 가설
`web` 잡이 `node --test web/app/test/*.test.mjs`로 네 스위트를 모두 돌리고, 래퍼가 `CI=true`에서 node가 없으면 실패하면 web 모듈 회귀가 조용히 지나가지 않는다. 추가 시간은 수십 초 이하다.
## 변경
- `.github/workflows/ci.yml` `web` 잡: `node --test web/app/test/*.test.mjs`(셸 글롭; node 22+ `--test`는 디렉터리를 받지 않는다).
- `tests/conftest.py`: `node` 픽스처(`node_path`)가 node가 없을 때 로컬은 skip, `CI=true`면 실패. 네 래퍼가 이 픽스처를 쓴다. 테스트 `tests/test_node_fixture.py`.
## 측정 지표와 측정창
머지 후 14일. 근거는 CI web 잡 로그와 gates 잡의 skip 목록.
- web 잡 node 단계의 `# pass`/`# fail`과 단계 시간.
- gates 잡에서 `test_web_*`의 skip 수.
## 성공 기준 (수치)
- 이 PR의 web 잡 로그에서 네 스위트가 모두 돌고 `# fail 0`(로컬 참고: tpgto 15·tells 10·personas 22·leaks 4 = 51개).
- node 단계 시간 중앙값 ≤ 60초.
- 측정창 안 gates 잡의 `test_web_*` skip 0건, 환경 문제로 인한 거짓 실패 0건.
## 롤백 방법
이 PR을 revert한다. web 잡은 tpgto만 돌리고, 래퍼는 node가 없으면 다시 skip한다.
## 결과 (측정창 종료 후 기록)
