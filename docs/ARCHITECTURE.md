# 아키텍처 (현재 상태를 반영해 유지할 것)

## 계층
- `stalker/` — 제품(L0)
  - `core/` — 카드(`cards.py`), 7카드 평가기(`evaluator.py`), MC 에퀴티(`equity.py`), 프리플랍 레인지(`ranges.py`, `data/preflop_equity.json` 필요 — 아직 미생성)
  - (예정) `tournament/` 설정·엔진, `agents/` 봇·상대모델·적응형 AI, `records/` 기록 스키마·저장, `pipeline/` 데이터 생성, `typing/` 스팟 택소노미·유형화, `service/` 학습 서비스
- `referee/` — 심판(보호 경로). 게이트·가드·지표.
- `harness/` — 하네스(L1/L2). 프로토콜, 루틴 지침, 스케줄, 훅, 실험 기록.
- `ops` 브랜치 — 운영 데이터(STATE, journal, metrics, reports).

## 핵심 설계 결정 (상세는 `docs/decisions/`)
- 카드 = `int` 0..51 (`rank = c >> 2`, `suit = c & 3`), 콤보 인덱스 0..1325 고정.
- 칩은 정수, 난수는 주입된 `numpy.random.Generator`.
- 기록은 버전이 붙은 JSONL(예정) — 1)의 출력이자 2)의 입력. 스키마는 기록 품질 게이트의 대상.
