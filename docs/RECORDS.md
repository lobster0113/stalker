# 기록 스키마 v1

결정 기록은 게임 생성(1)의 출력이자 유형화(2)·RL 학습의 입력이다. 코드: `stalker/records/schema.py`(스키마·검증), `stalker/records/store.py`(저장). 기준: ADR 0003 결정 6, `referee/DATA_SUFFICIENCY.md` D5, `referee/GATES.md` Gate L3.

## 저장 형식
런 디렉터리 하나 =
- `manifest.json` — `RunManifest`: `run_id`, `created_at`(UTC), `config`(`TournamentConfig.to_dict()`), `seed`, `git_sha`(로컬 변경이 있으면 `-dirty`), `policy_version`, `meta`, `schema_version`.
- `records.jsonl` — 한 줄에 하나: `{"type": "decision"|"hand"|"game", "record": {...}}`.

`RecordWriter`는 쓰기 전에, `iter_records`/`load_records`는 읽을 때 검증한다. 실패 메시지에는 `파일:줄`과 필드 경로가 붙는다. JSON에 NaN/Infinity는 쓰지 않으며, 읽을 때 만나면 `파일:줄`과 함께 거부한다(`action_logprob`·`action_values` 포함 모든 실수 필드).

## 식별자 (`RecordIds`)
| 필드 | 의미 |
|---|---|
| `episode_id` | RL 롤아웃 하나 |
| `game_id` | 토너먼트 한 판 — **기억 경계**(Gate L6: 서로 다른 game_id 간 상태 전달 없음) |
| `tournament_id` | 설정·시리즈 |
| `hand_id` | 게임 내 유일 |
| `decision_id` | 게임 내 유일 |
| `player_id` | 게임 내 플레이어 인덱스(좌석과 무관) |
| `policy_version` | 결정을 낸 정책 버전 |

## `DecisionRecord`
- `tournament_context`: `table_size`(2..9), `sb`, `bb`, `ante_type`(`none`/`classic`/`bb_ante`), `ante`, `level`(0부터), `remaining`, `paid_places`, `payout_vector`(1등부터, 길이 = `paid_places`), `next_level`(`[sb, bb, ante]` 또는 null), `stacks`(남은 전원 스택 요약: n·total·min·max·mean·median).
- `table_observation`: 행동자 본인이 볼 수 있는 것만. `seats`(≤9; seat·player_id·stack·bet·in_hand), `hero_seat`, `button`, `position`, `pot`, `hole_cards`(본인 2장), `board`, `street`, `current_hand_actions`(`[seat, 'f'|'cc'|'cbr', amount]`), `action_space`(`{kind: fold|call|raise, amount: raise-to}`), `legal_action_mask`(action_space와 정렬).
- `session_memory_snapshot`: 기억 켠 정책의 **요약**(`hands_observed`, 스칼라 `features`). 원시 로그는 넣지 않는다. 기억이 없으면 null.
- `probs_ai0`(기억 끔), `probs_ai1`(기억 켬; 해당 모델이 아직 없으면 null): action_space와 정렬된 확률.
- `acting_policy`(`ai0`/`ai1`), `chosen_action`(action_space 인덱스), `action_logprob`, `action_values`(선택, 액션별 가치), `policy_source`(`agent`, `checkpoint`, `meta`).

## `HandRecord` / `GameRecord`
- `HandRecord`: 핸드별 플레이어 `start_stack`·`final_stack`·`delta`, `busted`(이번 핸드 탈락 player_id), `terminal_flag`(게임을 끝낸 핸드면 true). 칩 증감은 보조 신호이며 보상이 아니다.
- `GameRecord`: player_id 순 `ranks`·`prizes`·`rewards`, `buy_in`, `hands`, `terminal_flag`(항상 true). **보상 = 상금 − 참가비**(희소, 게임 끝에만). `GameRecord.from_result(GameResult, buy_in, episode_id)`로 디렉터 결과에서 만든다.

## 검증 규칙 (`validate` → 위반 목록, `ensure_valid` → 예외)
- 로드 시: 필수 필드 존재, 미지 필드 거부, 타입(칩·id는 정수) — `from_dict`.
- 확률: 0 이상·유한, 합 = 1 ± 1e-6(`probs_ai0`, `probs_ai1`).
- 액션: `chosen_action`이 action_space 범위 안이고 `legal_action_mask`가 true, 행동 정책에서 확률 > 0, `action_logprob = log(p)` ± 1e-6. 길이 정렬(mask·probs·values).
- 관측: 보드 장수 = 스트리트, 홀카드 2장, 카드 중복 없음, hero 좌석의 player_id = `ids.player_id`.
- **타인 홀카드 부재**: 관측(홀카드·보드 제외)과 기억 요약 안의 모든 카드 문자열을 찾아 본인 홀카드·보드 밖의 카드가 있으면 위반. 실제 딜(`hole_cards={seat: cards}`)을 넘기면 타인 카드 포함 여부와 본인 카드 일치를 정확히 대조한다.
- 핸드: delta = final − start, 칩 보존(Σdelta = 0), `busted` = 0칩 플레이어.
- 게임: ranks는 1..n 순열, reward = prize − buy_in, `terminal_flag` = true.

## 버전
모든 레코드와 매니페스트에 `schema_version`(현재 1). 다른 버전은 로드를 거부한다(마이그레이션 필요). 스키마를 바꾸면 버전을 올리고 마이그레이션/호환 테스트를 함께 낸다.
