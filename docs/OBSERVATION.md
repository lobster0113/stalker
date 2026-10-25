# 관측 계약 (Observation Contract)

AI 정책이 보는 정보의 **유일한 출입구**는 `stalker/observe/builder.py`의 `ObservationBuilder.build(obs, memory) -> HeroObservation`이다 (ADR 0003 결정 2·3).
입력은 director의 `Observation`(본인 홀카드 + 공개 정보)과 본인의 `GameMemory`뿐이다.

## HeroObservation 필드
| 필드 | 의미 |
|---|---|
| `game_id`, `hand_id` | 식별자(공개) |
| `hole_cards`, `board` | **본인** 홀카드, 공개 보드 |
| `pot`, `pot_bb` | 현재 팟 (칩 / BB 단위) |
| `seats` | 길이 9 고정(`MAX_SEATS`). 슬롯 0 = 본인, 이후 시계 방향. `used=False`는 빈 좌석 마스크(값은 0). 토큰: 버튼·폴드 여부·올인·스택·베팅(칩/BB)·`player_id`, 그리고 상대면 이 게임 누적 통계 |
| `legal` | `fold/call/raise` 마스크, 콜 금액, 최소·최대 레이즈-투 (칩/BB) |
| `history` | 이번 핸드 공개 액션 `(본인 기준 슬롯, 'f'/'cc'/'cbr', 금액)` |
| `tournament` | 블라인드·앤티, 레벨 인덱스, 다음 레벨, 총/생존 인원, 지급 순위 수, 상금 벡터, 평균 스택, 본인 칩 순위, **스택 분포 9분위(min…max) 칩·BB** — 라운드 시작 시점의 전 테이블 합산(개별 타 테이블 로그는 없음) |
| `recent_actions` | 이 게임에서 본 최근 K개 공개 액션 `(hand_id, player_id, street, action, amount)` |
| `showdowns` | 이 게임의 공개 쇼다운 `(hand_id, player_id, 홀카드, 보드)` |

## 기억 경계 (`stalker/observe/memory.py`)
- `GameMemoryStore`는 `start_game(game_id)`로 생성, `end_game(game_id)`로 폐기. `NEW_HAND`는 핸드 단위 임시 상태만 초기화한다.
- 다른 `game_id`의 이벤트·조회·`build`는 `MemoryBoundaryError`. 활성 게임이 있는 채 `start_game`도 오류.
- 게임 중 합류: 합류 시점에 `start_game`하면 그 이후 이벤트만 누적된다.
- 상대(`player_id`)별 통계: 시야 내 핸드 수, 컨텍스트(`pre_open`/`pre_facing`/`post_open`/`post_facing`)별 기회 수와 fold/call/raise 횟수, VPIP·PFR 핸드 수, 쇼다운 수. 컨텍스트는 ACTION 이벤트의 `street`(보드 카드 수 0/3/4/5)와 `facing_bet`(액션 전 콜 금액 > 0)로 정한다. BB 체크는 자발적 참여(VPIP)가 아니다.

## 허용 / 금지
- 허용: 본인 홀카드, 공개 보드, 공개 액션, SHOWDOWN으로 공개된 카드, 공개 토너먼트 요약.
- 금지: 타인 비공개 카드, 덱 순서, 난수 시드/Generator, 타 테이블 개별 핸드 로그. `tests/test_observe.py`가 관측 객체를 재귀 순회해 허용 집합 밖 카드와 금지 필드명을 검사한다.

## 토너먼트 요약 보충
- `hero_rank`는 `all_stacks`와 같은 시점(라운드 시작)의 히어로 스택(`Observation.hand_start_stack`)으로 매긴다. `all_stacks`가 비어 있으면 `ValueError`(대체 분포를 쓰지 않는다).
- 핸드 도중 합류한 메모리는 그 핸드의 `NEW_HAND`를 못 봤으므로, 좌석 매핑이 없는 SHOWDOWN 항목은 건너뛰고 다음 핸드부터 기록한다.

## director `Observation`의 공개 보충 필드
- `ante_mode`: 이 핸드 레벨의 앤티 방식 `none|classic|bb_ante` (앤티가 0인 레벨은 `none`). 추론 대신 직접 읽는다.
- `action_order`: 이번 스트리트에서 아직 행동할 수 있는 좌석(폴드·올인 제외)을 현재 행동자부터 시계 방향으로 나열. 프리플랍 첫 행동자는 UTG(헤즈업은 버튼=SB). 둘 다 공개 정보이며 기본값(`"none"`, `()`)으로 기존 생성자 호출과 호환된다. RL `HeroObservation`은 아직 쓰지 않는다.
