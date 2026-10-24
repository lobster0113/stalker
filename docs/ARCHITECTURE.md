# 아키텍처 (현재 상태를 반영해 유지할 것)

## 계층
- `stalker/` — 제품(L0)
  - `core/` — 카드(`cards.py`), 7카드 평가기(`evaluator.py`), MC 에퀴티(`equity.py`), ICM(`icm.py`: Malmuth-Harville 정확해 `icm_equity`(생존자 ≤9) + Gumbel-max 몬테카를로 `icm_equity_mc`, 0 스택=탈락·하위 지급 제외), 프리플랍 레인지(`ranges.py`, `data/preflop_equity.json`: 169 클래스 × 랜덤 상대 1~5명 에퀴티, `python -m stalker.tools.build_tables`로 고정 시드 재생성)
  - `tools/` — 오프라인 도구(`build_tables.py`: 프리플랍 에퀴티 테이블, `bench_engine.py`: 엔진 처리량 벤치, `diff_engine.py`: `FastHand`↔PokerKit 차등 테스트)
  - `tournament/` — 토너먼트 설정 스키마(`config.py`: `TournamentConfig`·페이아웃 생성기·`level_at`/`next_level`, JSON 직렬화, `schema_version`=1)와 `presets/*.json`(`python -m stalker.tools.build_presets`로 재생성). `hand.py`: PokerKit 0.7.7(버전 고정) 위의 NLHE 핸드 래퍼 `Hand` — 테이블 좌석 기준 스택(0=빈 좌석)·버튼·SB/BB·앤티(`none`/`classic`/`bb_ante`), 합법 액션 조회·적용, 종료 시 `HandResult`(좌석별 최종 스택·증감, 메인/사이드 팟과 적격 좌석, 팟 지급). 카드는 주입된 `Generator`로 섞은 자체 덱에서만 딜(재현성), `to_phh()`/`replay_phh_final_stacks()`로 PHH 왕복. 러너는 `director.py`(아래). `fast_hand.py`: `FastHand` — `Hand`와 같은 인터페이스의 순수 파이썬 고속 엔진(ADR 0005). PokerKit 규칙·덱 소비 순서를 복제해 같은 시드·액션이면 합법 액션 집합과 `HandResult`가 동일(`stalker.tools.diff_engine`으로 차등 검사), PHH 내보내기는 없음
  - `tournament/director.py` — `run_game(config, agents, rng, observer)`: 라운드마다 모든 테이블이 한 핸드씩(레벨 = 라운드 번호), 동시 탈락은 핸드 시작 스택이 큰 쪽이 상위 순위(동률은 주입 rng 추첨), 테이블 해체·밸런싱(차 ≤ 1, 이동자는 임의 빈 좌석), 페이아웃 → `GameResult`(순위·상금·핸드 수·불법 액션 수). `length_unit=minutes`·`short_stack_rule=skip`은 미구현(명시적 `ConfigError`). 식별자 `game_id`/`tournament_id`/`hand_id`(게임 내 유일)/`player_id`(= agents 인덱스) 분리.
  - `agents/` — `base.py`: `Agent`(`act`/`observe`/`on_game_start`/`on_game_end`), 플레이어별 `Observation`(자신의 홀카드와 공개 정보만), 공개 `Event`(`START_GAME`/`NEW_HAND`/`ACTION`/`SHOWDOWN`/`HAND_END`/`END_GAME`; 홀카드는 SHOWDOWN에서만 공개). 불법 액션은 체크/폴드로 대체하고 `illegal_actions`로 집계. `random_agent.py`: Gate R용 무작위 합법 봇.
  - `observe/` — 관측 계약(`docs/OBSERVATION.md`): `builder.py`(`ObservationBuilder` → 9좌석 고정 `HeroObservation`, 스택 분포 분위수 요약), `memory.py`(`GameMemoryStore`: game_id 경계, 상대별 컨텍스트 통계·최근 K 액션·공개 쇼다운). director의 `Observation.all_stacks`(라운드 시작 전 생존자 스택, 비면 오류)·`hand_start_stack`(히어로의 핸드 시작 스택, `hero_rank` 산출용)와 ACTION 이벤트의 `street`/`facing_bet`가 입력.
  - `records/` — 기록 스키마 v1(`schema.py`, 상세 `docs/RECORDS.md`): `DecisionRecord`(식별자 7종 분리, 토너먼트 맥락, 본인 관측, 기억 요약, `probs_ai0`/`probs_ai1`, 선택 액션·logprob), `HandRecord`, `GameRecord`(보상 = 상금 − 참가비). 타입 검사 `from_dict`와 규칙 검증 `validate`(확률합·합법 액션·타인 홀카드 부재). `store.py`: 런 디렉터리 = `manifest.json`(설정·시드·git sha·policy_version) + `records.jsonl`, 쓰기·읽기 모두 검증.
  - (예정, ADR 0002) `oracle/` 프리플랍 ICM 솔버·TexasSolver 연동·전략 라이브러리, `adapt/` 상대 모델·적응 계층, `agents/` 벤치마크 봇(기본 인터페이스는 구현됨), `pipeline/` 데이터 생성, `typing/` 스팟 택소노미·유형화, `service/` 학습 서비스
- `referee/` — 심판(보호 경로). 게이트·가드·지표.
  - `anchors/` — 이론 기준선. `hu_equity.py`: numpy 벡터화 7카드 평가기(`evaluate`와 점수 동일) + 169×169 클래스 올인 에퀴티 `E`·비충돌 콤보 쌍 수 `N`(`data/hu_class_equity.json`, `python -m referee.anchors.hu_equity`로 고정 시드 재생성). `icm_reference.py`: ICMizer-등가 참조기 v1 — 액션 순서 스택(끝 2석 = SB·BB)·일반/BB 앤티·페이아웃의 푸시/폴드·단일 콜러 트리를 역귀납 평가, 가상 플레이로 플레이어별 BR 이득 ≤ 상금풀×`tol`(기본 0.1%)까지 수렴. 가치 모델 `icm`(해당 핸드 탈락자는 그 순위 상금)·`chipev`, `fgs_depth` d면 말단을 다음 핸드(버튼 1칸) 깊이 d−1 해로 평가. `evaluate_spot(policy_fn, spot, opponents, hero)`: 고정 상대(내시 `Solution` 또는 `top_percent_strategy` 같은 `Strategy`) 대비 히어로 기대 상금·BR 대비 손실. 한계(오버콜 없음, 비참여자 카드 제거 무시, 포스팅 올인 스팟 거부)는 모듈 문서에.
  - `stats.py` — 클러스터 부트스트랩 백분위 CI(`bootstrap_ci`), 정규 SPRT(`sprt`, 무익성 중단 전용), `noninferiority`/`superiority`(CI 하한 판정), `required_tournaments`(검정력 0.9·α 0.05 블록 수).
  - `evaluate.py` — `evaluate(config, candidate, baseline, blocks, seed, rotations)`: 블록마다 같은 게임 시드로 연속 블록 A/B 마스크의 `rotations`개 순환 이동과 각 보완 마스크(좌석 교환)를 플레이하는 duplicate 평가(이동마다 서로 다른 마스크, 짝수 인원은 `rotations` ≤ n/2), 블록 = 부트스트랩 클러스터. `EvalResult.to_json()`에 설정·시드 정책·참조기 버전·블록별 diff 기록.
  - `gate_r/` — Gate R 규칙 정확성 스위트(`python -m referee.gate_r [--full]`, `gates full`에 등록, 지표 `gate_r_pass_rate`). `evaluator.py`(독립 7장 평가기)·`settlement.py`(독립 사이드팟 정산: 앤티 데드 머니, 레이어 분할, 못 이기는 핸드 머크 후 같은 좌석 팟 병합, 홀수 칩은 버튼 왼쪽 첫 승자)·`checks.py`(공개 이벤트 스트림을 독립 규칙 모델로 재생해 항목별 `Tally`)·`suite.py`(프리셋 × fast 구조 변형 × 봇 × 시드). PokerKit·`stalker.tournament.hand`를 import하지 않는다(테스트로 강제).
- `harness/` — 하네스(L1/L2). 프로토콜, 루틴 지침, 스케줄, 훅, 실험 기록.
- `ops` 브랜치 — 운영 데이터(STATE, journal, metrics, reports).

## 핵심 설계 결정 (상세는 `docs/decisions/`)
- 카드 = `int` 0..51 (`rank = c >> 2`, `suit = c & 3`), 콤보 인덱스 0..1325 고정.
- 칩은 정수, 난수는 주입된 `numpy.random.Generator`.
- 기록은 버전이 붙은 JSONL(`stalker/records/`, `schema_version`=1) — 1)의 출력이자 2)의 입력. 스키마는 기록 품질 게이트(D5)의 대상.
