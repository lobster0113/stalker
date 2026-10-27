# web/ — 학습 서비스 웹앱

## demo/ (D1, AI 없음)
- `demo/index.html` 한 파일. 빌드·외부 의존 없음(글꼴만 Google Fonts, 없으면 시스템 글꼴). 브라우저로 열면 동작한다.
- 화면: 시작(설정 1/1-1/1-2/2, TP 등급) · 훈련 게임(테이블 중앙, TP 패널 오른쪽/폰은 바텀 시트, 다른 플레이어 1.5초 진행) · 학습 섹션(항목별 쉬움/보통/어려움) · 복기(핸드 입력 → 비교 → 비슷한 상황으로 훈련).
- 채점 정답은 **모의값**이다: 관측 통계의 수축 추정, 몬테카를로 에퀴티, 규칙 기반 혼합 전략. 실제 TP-GTO는 D3에서 연결한다(`docs/decisions/0009-tp-gto-design-proposal.md`).
- TP 항목 ID·등급·눈금·적용 조건은 TP v0.1(`docs/TP.md`, `stalker/tp/spec/tp_v0_1.json`)을 따른다. `TP` 키와 `TIERS[*].items`는 JSON과 정확히 같아야 하며 `tests/test_tp_spec.py::test_demo_matches_spec`이 검사한다. 명세가 바뀌면 이 파일의 `TP`·`TIERS`도 같은 PR에서 고친다.
- 모든 정답 화면(훈련 게임 채점·학습 섹션·복기)에 신뢰도 라벨 `모의`를 붙인다. 액션은 Q값이 없으므로 "모의 참고: TP-GTO(모의) 혼합 전략"으로만 보여주고 점수·약점에 넣지 않으며 EV 손실 수치도 내지 않는다(TP §5). `plan.pot`은 채점하지 않는 성찰 질문(중수·고수)이고, `opp.*`는 기회 수(N/A 기준은 JSON `na.min_opportunities`)가 모자라면 묻지 않는다.
- 결정당 입력 시간(내 차례 시작 → 제출)을 기록해 "내 약점" 화면에 P50/P95로 보여준다(브라우저 localStorage `stalker.itimes`, 최근 300회).
- 사용자에게 보여줄 때: 대화 세션이 `<!doctype>`·`<html>`·`<head>`·`<body>` 태그를 뺀 사본을 Claude Artifact(비공개)로 게시한다. 현재 게시본: https://claude.ai/artifact/LpQTDzYgZgTjcY5T4BwcZb

## 다음 (Gate U, `referee/GATES.md`)
- Playwright E2E + 3종 화면 스크린샷 CI 잡(`web`)이 생기면 실행 명령을 여기에 적는다.
