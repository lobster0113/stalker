# web/ — 학습 서비스 웹앱

## demo/ (D1, AI 없음)
- `demo/index.html` 한 파일. 빌드·외부 의존 없음(글꼴만 Google Fonts, 없으면 시스템 글꼴). 브라우저로 열면 동작한다.
- 화면: 시작(설정 1/1-1/1-2/2, TP 등급) · 훈련 게임(테이블 중앙, TP 패널 오른쪽/폰은 바텀 시트, 다른 플레이어 1.5초 진행) · 학습 섹션(항목별 쉬움/보통/어려움) · 복기(핸드 입력 → 비교 → 비슷한 상황으로 훈련).
- 채점 정답은 **모의값**이다: 관측 통계의 수축 추정, 몬테카를로 에퀴티, 규칙 기반 혼합 전략. 실제 TP-GTO는 D3에서 연결한다(`docs/decisions/0009-tp-gto-design-proposal.md`).
- TP 항목 ID·등급·눈금은 `docs/TP.md` v0과 같다. 명세가 바뀌면 이 파일의 `TP`·`TIERS`도 같은 PR에서 고친다.
- 사용자에게 보여줄 때: 대화 세션이 `<!doctype>`·`<html>`·`<head>`·`<body>` 태그를 뺀 사본을 Claude Artifact(비공개)로 게시한다. 현재 게시본: https://claude.ai/artifact/LpQTDzYgZgTjcY5T4BwcZb

## 다음 (Gate U, `referee/GATES.md`)
- Playwright E2E + 3종 화면 스크린샷 CI 잡(`web`)이 생기면 실행 명령을 여기에 적는다.
