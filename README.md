# STALKER

사람이 따라 할 수 있는 GTO(TP-GTO)와, 그것으로 초보가 고수까지 빨리 오르게 돕는 개인용 포커 학습 서비스.
이 리포는 **사람이 아니라 AI 에이전트 하네스가 개발·운영한다.**

- 목적과 원문 요구사항: [`docs/CHARTER.md`](docs/CHARTER.md), [`docs/ORIGIN.md`](docs/ORIGIN.md), Thinking Process: [`docs/TP.md`](docs/TP.md)
- 하네스 설계: [`docs/HARNESS_DESIGN.md`](docs/HARNESS_DESIGN.md)
- 에이전트 진입점: [`CLAUDE.md`](CLAUDE.md)
- 운영 상태: `ops` 브랜치의 `STATE.md`, 지표 `metrics/history.jsonl`, 하네스 리포트 `reports/`
- 긴급 정지: main에 `harness/PAUSE` 파일을 추가하면 모든 루틴이 멈춘다(감사 제외).
