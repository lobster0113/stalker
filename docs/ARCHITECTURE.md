# 아키텍처 (현재 상태를 반영해 유지할 것)

## 계층
- `stalker/` — 제품(L0)
  - `core/` — 카드(`cards.py`), 7카드 평가기(`evaluator.py`), MC 에퀴티(`equity.py`), ICM(`icm.py`: Malmuth-Harville 정확해 `icm_equity`(생존자 ≤9) + Gumbel-max 몬테카를로 `icm_equity_mc`, 0 스택=탈락·하위 지급 제외), 프리플랍 레인지(`ranges.py`, `data/preflop_equity.json`: 169 클래스 × 랜덤 상대 1~5명 에퀴티, `python -m stalker.tools.build_tables`로 고정 시드 재생성)
  - `tools/` — 오프라인 생성 도구(`build_tables.py`: 프리플랍 에퀴티 테이블)
  - `tournament/` — 토너먼트 설정 스키마(`config.py`: `TournamentConfig`·페이아웃 생성기·`level_at`/`next_level`, JSON 직렬화, `schema_version`=1)와 `presets/*.json`(`python -m stalker.tools.build_presets`로 재생성). `hand.py`: PokerKit 0.7.7(버전 고정) 위의 NLHE 핸드 래퍼 `Hand` — 테이블 좌석 기준 스택(0=빈 좌석)·버튼·SB/BB·앤티(`none`/`classic`/`bb_ante`), 합법 액션 조회·적용, 종료 시 `HandResult`(좌석별 최종 스택·증감, 메인/사이드 팟과 적격 좌석, 팟 지급). 카드는 주입된 `Generator`로 섞은 자체 덱에서만 딜(재현성), `to_phh()`/`replay_phh_final_stacks()`로 PHH 왕복. 러너는 `director.py`(아래)
  - `tournament/director.py` — `run_game(config, agents, rng, observer)`: 라운드마다 모든 테이블이 한 핸드씩(레벨 = 라운드 번호), 동시 탈락은 핸드 시작 스택이 큰 쪽이 상위 순위(동률은 주입 rng 추첨), 테이블 해체·밸런싱(차 ≤ 1, 이동자는 임의 빈 좌석), 페이아웃 → `GameResult`(순위·상금·핸드 수·불법 액션 수). `length_unit=minutes`·`short_stack_rule=skip`은 미구현(명시적 `ConfigError`). 식별자 `game_id`/`tournament_id`/`hand_id`(게임 내 유일)/`player_id`(= agents 인덱스) 분리.
  - `agents/` — `base.py`: `Agent`(`act`/`observe`/`on_game_start`/`on_game_end`), 플레이어별 `Observation`(자신의 홀카드와 공개 정보만), 공개 `Event`(`START_GAME`/`NEW_HAND`/`ACTION`/`SHOWDOWN`/`HAND_END`/`END_GAME`; 홀카드는 SHOWDOWN에서만 공개). 불법 액션은 체크/폴드로 대체하고 `illegal_actions`로 집계. `random_agent.py`: Gate R용 무작위 합법 봇.
  - `records/` — 기록 스키마 v1(`schema.py`, 상세 `docs/RECORDS.md`): `DecisionRecord`(식별자 7종 분리, 토너먼트 맥락, 본인 관측, 기억 요약, `probs_ai0`/`probs_ai1`, 선택 액션·logprob), `HandRecord`, `GameRecord`(보상 = 상금 − 참가비). 타입 검사 `from_dict`와 규칙 검증 `validate`(확률합·합법 액션·타인 홀카드 부재). `store.py`: 런 디렉터리 = `manifest.json`(설정·시드·git sha·policy_version) + `records.jsonl`, 쓰기·읽기 모두 검증.
  - (예정, ADR 0002) `oracle/` 프리플랍 ICM 솔버·TexasSolver 연동·전략 라이브러리, `adapt/` 상대 모델·적응 계층, `agents/` 벤치마크 봇(기본 인터페이스는 구현됨), `pipeline/` 데이터 생성, `typing/` 스팟 택소노미·유형화, `service/` 학습 서비스
- `referee/` — 심판(보호 경로). 게이트·가드·지표.
- `harness/` — 하네스(L1/L2). 프로토콜, 루틴 지침, 스케줄, 훅, 실험 기록.
- `ops` 브랜치 — 운영 데이터(STATE, journal, metrics, reports).

## 핵심 설계 결정 (상세는 `docs/decisions/`)
- 카드 = `int` 0..51 (`rank = c >> 2`, `suit = c & 3`), 콤보 인덱스 0..1325 고정.
- 칩은 정수, 난수는 주입된 `numpy.random.Generator`.
- 기록은 버전이 붙은 JSONL(`stalker/records/`, `schema_version`=1) — 1)의 출력이자 2)의 입력. 스키마는 기록 품질 게이트(D5)의 대상.
