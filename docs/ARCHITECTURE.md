# 아키텍처 (현재 상태를 반영해 유지할 것)

## 계층
- `stalker/` — 제품(L0)
  - `core/` — 카드(`cards.py`), 7카드 평가기(`evaluator.py`), MC 에퀴티(`equity.py`), 프리플랍 레인지(`ranges.py`, `data/preflop_equity.json`: 169 클래스 × 랜덤 상대 1~5명 에퀴티, `python -m stalker.tools.build_tables`로 고정 시드 재생성)
  - `tools/` — 오프라인 생성 도구(`build_tables.py`: 프리플랍 에퀴티 테이블)
  - `tournament/` — 토너먼트 설정 스키마(`config.py`: `TournamentConfig`·페이아웃 생성기·`level_at`/`next_level`, JSON 직렬화, `schema_version`=1)와 `presets/*.json`(`python -m stalker.tools.build_presets`로 재생성). 러너는 예정(PokerKit 위)
  - (예정, ADR 0002) `oracle/` 프리플랍 ICM 솔버·TexasSolver 연동·전략 라이브러리, `adapt/` 상대 모델·적응 계층, `agents/` 벤치마크 봇, `records/` 기록 스키마·저장, `pipeline/` 데이터 생성, `typing/` 스팟 택소노미·유형화, `service/` 학습 서비스
- `referee/` — 심판(보호 경로). 게이트·가드·지표.
- `harness/` — 하네스(L1/L2). 프로토콜, 루틴 지침, 스케줄, 훅, 실험 기록.
- `ops` 브랜치 — 운영 데이터(STATE, journal, metrics, reports).

## 핵심 설계 결정 (상세는 `docs/decisions/`)
- 카드 = `int` 0..51 (`rank = c >> 2`, `suit = c & 3`), 콤보 인덱스 0..1325 고정.
- 칩은 정수, 난수는 주입된 `numpy.random.Generator`.
- 기록은 버전이 붙은 JSONL(예정) — 1)의 출력이자 2)의 입력. 스키마는 기록 품질 게이트의 대상.
