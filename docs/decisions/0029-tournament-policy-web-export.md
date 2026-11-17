# ADR 0029: 토너먼트 단계 정책의 웹 내보내기·표시 경로 (F8a)

- 상태: 제안. 이 PR이 머지되면 채택한다(Builder 추천안으로 진행, `harness/PROTOCOL.md` §9).
- 이슈: #945 (ADR 0027 후속 F8, #385 기준 5). 관련: ADR 0019 §7, ADR 0021(인원별 정책 파일), ADR 0022(c1 백오프), ADR 0027(env_id·stage·key `t<stage><ante>`), #588·#596(`cloud.yml mode=export`), #775(L1 행 바이트), #887(웹 미러 앤티).
- **직접 돌린 수치는 없다.** 파일 크기는 현재 `web/app/policy/`의 `ls` 값(참고용)이고, 단계 수·run 수에 따른 총량은 **가정**이다. 성능 판단은 CI 결과만 근거다.
- **범위**: 형식·경로·표시 규칙만 정한다. 어떤 run이 어느 단계의 정책이 될지는 #937(F6c-2)·F7a 결과 뒤에 정하므로 이 ADR은 run 선택과 무관하다. 코드·`cloud.yml`·정책 파일은 바꾸지 않는다.

## 맥락
현재 웹 정책은 캐시게임 전용이다(`web/app/policy/index.json`: `schema_version` 1, `tiers[tier]`(6인)와 `tiers[tier].by_players["<n>"]`). 정책 파일(`stalker.web.policy` v2)은 key → 1/255 양자화 행이고, 한 파일 상한은 3MiB(`export_web_policy.MAX_BYTES`, 초과는 `--min-visits`로 거르고 `l1_rows`를 동봉). `cloud.yml mode=export`는 **mixn c1 캐시 run**(2–6인)만 받는다(`export_run`·`export_tier` 입력, `export_web_players export`).
웹 토너먼트 모드(`web/demo/index.html`)는 정책이 없어 pill이 "토너먼트 · 모의 정답"(`index.html` ~2215행의 else 가지)이고 정답은 규칙 기반 모의값이다.
ADR 0027이 정한 학습 단위: 정책 하나 = (프리셋 env_id, stage, 앤티 유무, 학습 λ·스택 분포). 같은 key 문자열이라도 보상(ICM)이 달라 **캐시 정책과 섞으면 안 된다**(CHARTER 환경 분리, RFC-08).

## 결정 1. 인덱스 형식
**결정: `index.json`은 `schema_version` 2로 올리고 최상위에 `tournament` 맵을 추가한다. 기존 `tiers`는 한 글자도 바꾸지 않는다.**

```json
{ "schema": "stalker.web.policy-index", "schema_version": 2,
  "tiers": { ...기존 그대로... },
  "tournament": {
    "<env_id>": {                       // from_tournament(preset)이 낸 값, 예 9max_sng_503020의 env_id
      "<stage>": {                      // e | b | m | f (ADR 0027 결정 2)
        "ante": { "0": <entry>, "1": <entry> }   // key의 `<ante>` 칸. 학습된 것만 있다
      } } } }
```
- `<entry>`는 기존 `index_entry` 필드(`file`·`bytes`·`run_id`·`sha`·`lbr_bb`·`key_variant`·`min_visits`·`keys`…)에 다음을 더한다: `env_id`, `stage`, `ante`, `payoff: "icm"`, `lam`, `stacks`(학습 스택 표본, 예 `bubble:skewed`), `level_index`, `players`(= 학습 때의 생존자 수 r; SNG 버블은 4), `trained_on`(`game: "tournament"`, 프리셋, 단계). 값은 학습 결과의 `train_env`(ADR 0027 F2)에서 그대로 가져온다 — 추정해서 채우지 않는다.
- **호환**: v1 리더는 `tournament`를 모르고 무시한다(기존 코드는 `idx.tiers`만 읽는다). v2 리더는 `schema_version`이 1이면 `tournament`를 `{}`로 본다. `upsert_index`는 `tiers`를 건드리지 않고 `tournament`만 갱신한다(기존 6인 키 보존 규칙과 같은 방식). 따라서 기존 캐시 파일·인덱스 바이트는 토너먼트 정책이 없는 한 **`schema_version` 숫자 하나만** 다르다. 이 한 글자 차이는 마이그레이션 테스트(v1 → v2 읽기, v2에서 `tiers` 불변)로 고정한다(CLAUDE.md 스키마 규칙).
- 대안(별도 `tournament-index.json`) 기각: 페이지가 인덱스를 이미 한 번 받아 모델 목록을 그린다. 파일이 둘이면 요청이 하나 늘고 두 파일이 어긋날 수 있다. 토너먼트 항목은 작아(항목당 수백 바이트) 합쳐도 부담이 없다.
- 학습 λ·스택은 키가 아니라 **메타**다. 같은 (env, stage, ante)에 정책이 둘이면(예: λ 0 대 선택값) 인덱스에는 **채택된 하나만** 싣는다(채택 판정은 F7). 후보 비교는 ops 기록에 둔다.
- 파일 이름: `web/app/policy/t-<env_id>-<stage><ante>.json`(예 `t-<env_id>-b0.json`). 학습 key는 같은 c1 key이므로 `key_variant: "c1"`, 정책 파일 스키마(`stalker.web.policy`)는 **바꾸지 않는다**(메타 필드만 더 붙는다; 파일 `schema_version` 2 유지, 리더는 모르는 메타를 무시).

## 결정 2. 내보내기 경로
**결정: 같은 `cloud.yml`의 `mode=export`를 넓히되, 입력 `export_kind`(기본 `cash`)를 더해 `cash`(지금 동작)와 `tournament`를 분기한다. 새 모드는 만들지 않는다. 변경은 `.github/`와 `export_web_players.py`에 걸치므로 구현은 `harness-change` 후속 이슈(H1)로 분리한다.**
- 근거: 러너가 하는 일(artifact 확인 → pod 결과 받기 → 문턱 적용 → 파일·인덱스·요약 → `ops:cloud/policies/<run>/`에 올림)은 캐시와 같다. 다른 점은 입력 검증(인원 혼합 `by_players` 대신 `train_env`가 있는 단일 run)과 출력 파일명·인덱스 위치뿐이다. 모드를 하나 더 두면 `check|run|reap|collect|export` 허용 목록·그룹 락·권한이 중복된다. 반대로 `export_kind=cash`가 기본이면 기존 호출·바이트는 불변이다.
- 입력(후속 H1이 정한다): `export_run`(run id), `export_kind=tournament`, `export_stage`·`export_ante`는 **필요 없다** — 둘 다 `train_env`에서 읽는다. 결과에 `train_env`가 없거나 `payoff != "icm"`이면 거부한다(캐시 run을 토너먼트로 잘못 내보내는 사고 방지). `export_tier`는 persona 등급이 아니라 정책 등급(예 `mid`)을 그대로 쓴다.
- 산출: `ops:cloud/policies/<run>/t-<env_id>-<stage><ante>.json`과 `index.json`(위 v2 형식). 사람이 아닌 에이전트가 이 파일을 `web/app/policy/`로 옮겨 PR을 연다(기존 캐시 경로와 같은 절차, #596).
- 하네스 경로 변경이 필요한 부분: `.github/workflows/cloud.yml`의 입력·검증(H1). `export_web_players.py`·`export_web_policy.py`는 `stalker/`라서 harness-change 불필요하지만 같은 이슈에 묶는 편이 테스트가 편하므로 H1에 포함한다.
- 지금 ADR에서는 **이 경로가 바뀌지 않는다**(`cloud.yml` 미수정).

## 결정 3. 바이트 상한과 총량
- **파일당 상한은 지금과 같은 3MiB**(`MAX_BYTES`, 페이지가 첫 핸드 전에 받는 크기, #336). 현재 값(참고용): `mid-2/3/6.json` 약 3.0MiB(상한에 닿음, `--min-visits`로 거른 결과), `mid-4` 2.2MiB, `mid-5` 2.9MiB. 하나의 토너먼트 정책은 한 인원(예 4인 버블) 키만 갖는다. 캐시 2–6인 혼합 run에서 인원별로 나눈 파일이 이미 3MiB 안이므로, **단일 인원 학습 정책은 같은 문턱 절차로 3MiB 안에 들어온다고 가정**한다(키 수는 `t<stage>` 한 칸 고정이라 오히려 적다. 가정 — 첫 export에서 검증).
- 넘으면 캐시와 같은 순서: `--min-visits`(문턱) → `l1_rows` 동봉(#803) → 그래도 넘으면 파일은 쓰되 `over_budget` 표시와 함께 후속 이슈로 올린다(`export_web_players`가 이미 하는 동작).
- **총량(가정)**: 현재 `web/app/policy/` 전체는 약 24MB(고수 9.3MB 포함, 참고용). 토너먼트 단계 정책을 단계·앤티마다 두면 정책 파일이 (정책 있는 (env, stage, ante) 수) × 최대 3MiB 늘어난다. **총량 상한을 새로 둔다: 토너먼트 정책 파일 합계 ≤ 12MiB(약 4 파일 × 3MiB)**, 이를 넘기는 export는 H1의 검사가 거부한다. 근거: 첫 목표는 SNG 버블(b0)·m·앤티(b1) 정도(ADR 0027 단계 1–3)이고 정책은 **그 (env, stage)로 들어갈 때만 지연 로드**한다(결정 4) — 초기 페이지 로드에는 인덱스(항목당 수백 바이트)만 들어간다. 12MiB는 가정이며 정책이 5개를 넘으면 ADR 0021·#775 방식(문턱 상향 또는 gzip 전송)으로 다시 본다. gzip 전송 여부는 지금 호스팅(정적 파일)이 어떻게 압축하는지에 달려 있어 이 ADR에서 정하지 않는다.
- 로드 시점: 캐시 정책은 설정 화면에서 인원이 정해질 때 읽는다. 토너먼트 정책도 같은 규칙으로 **게임을 시작할 때 그 (env, stage, ante)의 파일 하나만** 읽는다. 게임 도중 단계가 바뀌면(예 버블 → 상금권) 새 단계 정책이 있을 때 그 시점에 읽고, 읽는 동안 이전 정책(또는 규칙 봇)으로 계속한다(UI는 멈추지 않는다).

## 결정 4. 웹 런타임 규칙과 표시 문구
조회 키는 (현재 프리셋 env_id, 현재 단계 stage, 현재 레벨의 앤티 유무). 단계는 ADR 0027 결정 2의 정의(`r`, K, 한 테이블 여부)를 웹이 이미 가진 상태(`G.players`·`G.paid`·`G.stage`)로 계산한다 — 웹의 `STAGE_NAMES`와 ADR의 `e|b|m|f` 대응표는 H2에서 테스트로 고정한다.

| 경우 | 동작 | pill 문구(`pill.textContent`) | 툴팁(`pill.title`) |
|---|---|---|---|
| (env, stage, ante) 정책 있음 | 그 정책이 모든 AI 좌석을 구동. key 미스는 ADR 0022 백오프(L1–L3)로 | `토너먼트 · <단계명> · TP-GTO` | "이 설정의 <단계명>(ICM 보상)에서 학습한 정책이에요." + `modelLine`(run·반복·LBR) |
| 정책 있음, 이번 결정만 key 미스(백오프 끝까지 균등) | 해당 결정만 규칙 봇 값으로 대체(균등 아님). 같은 판에서 미스 비율을 센다 | 변경 없음 | 미스가 있으면 "일부 스팟은 규칙 봇이 대신했어요(n/m)." 덧붙임 |
| env는 같지만 **이 단계 정책 없음**(예 정책은 버블만 있고 지금은 상금권 안) | 규칙 봇. 정책이 있는 단계로 들어오면 즉시 전환 | `토너먼트 · <단계명> · 미학습(규칙 봇)` | "이 단계의 TP-GTO는 아직 학습 중이에요. 상대·정답은 규칙 기반입니다." |
| env에 **토너먼트 정책이 하나도 없음**(다른 프리셋) | 규칙 봇(현재 동작) | `토너먼트 · 모의 정답`(**현재 문구 유지**) | 현재 툴팁 유지 |
| 로드 실패(네트워크 등) | 현재 캐시 경로의 `error` 상태와 같은 재시도·"모의 정답으로 계속" | `모의 정답 · 정책 연결 실패`(현재 문구) | `TPG.err` |

- 복기(리뷰) 화면: 판을 **치른 당시**의 (env, stage, ante)로 비교 정책을 고른다. 정책이 없으면 현재 "복기 · 모의 정답"과 같다. 복기에서 "정답"이라 부를 때 **정책이 있는 단계만** TP-GTO 표시를 쓴다(채점 신뢰도 오표시 방지, TP.md 계약).
- 규칙 봇 백오프는 캐시 규칙을 그대로 쓴다(`backoffRow`). **캐시 정책으로 토너먼트를 대신하지 않는다**: 보상이 달라 ICM 상황에서 틀린 행동을 "TP-GTO"라고 부르게 된다(RFC-08).
- 학습 정책이 속한 인원(r)과 실제 생존자 수가 다르면(예 정책은 4인, 지금 5인 버블) 정책 없음으로 본다. 인원 칸 `n<players>`가 key에 있으므로 미스 비율로 숨기지 않고 표시도 "미학습"으로 한다.

## 결정 5. 후속 이슈 초안
(권한 라벨은 Planner가 붙인다.)

**H1. `cloud.yml mode=export` 토너먼트 입력 + 인덱스 v2 (area:harness, area:service, harness-change)**
- [ ] `export_kind=tournament`(기본 `cash`, 값 검증)로 `train_env`가 있고 `payoff=icm`인 단일 run을 `t-<env_id>-<stage><ante>.json`과 v2 `index.json`으로 `ops:cloud/policies/<run>/`에 낸다.
- [ ] `export_kind=cash`(기본) 출력은 이슈 전과 **바이트 동일**(단 `index.json`의 `schema_version`만 2).
- [ ] v1 인덱스 읽기·v2에서 `tiers` 불변·`train_env` 없는 run 거부·합계 12MiB 초과 거부를 테스트로 확인. 문서(ARCHITECTURE.md, web/README.md) 갱신.

**H2. 웹 토너먼트 정책 로드·단계 매핑 (area:service)** — 선행 H1, 정책 파일 1개 이상
- [ ] `tpgto.js`에 인덱스 v2 읽기, (env_id, stage, ante) 조회, 단계 정의 함수(`e|b|m|f` ↔ 웹 `G.stage`, 인원·상금 인원·테이블 수로 계산)를 둔다. 단위 테스트(Node)로 경계(r = K+1 → b, r ≤ K → m)를 고정.
- [ ] 정책이 있는 단계에서 AI 좌석이 그 정책으로 행동하고 key 미스는 백오프(ADR 0022), 없는 단계는 규칙 봇. 단계가 바뀔 때 정책이 전환되고 로드 중에는 이전 정책으로 계속(Gate U 시나리오).

**H3. 표시 문구·복기 일치 (area:service)** — 선행 H2
- [ ] 결정 4 표의 5가지 경우에 대한 pill·툴팁을 Gate U 스크린샷·텍스트 검사로 확인(경우마다 한 장면).
- [ ] 복기가 판 당시의 (env, stage, ante)로 비교 정책을 고르고, 정책 없는 단계에서 "TP-GTO" 문구가 나오지 않는다.
- [ ] 로드 실패 경로가 캐시와 같은 재시도·모의 계속을 지원한다.

**H4. 첫 실제 export + 파일 반입 (area:ai, area:service)** — 선행 H1, #937 판정, F5의 채택 run
- [ ] 채택된 SNG 버블 run을 H1 경로로 내보내 `web/app/policy/`에 파일·인덱스 항목을 넣는다. 파일 ≤ 3MiB(초과 시 문턱·`l1_rows`), 합계 ≤ 12MiB, 인덱스 메타가 `train_env`와 일치(테스트).
- [ ] `e3_web_lbr` 같은 기존 웹 정책 LBR 검사가 토너먼트 항목에서 깨지지 않거나(해당 없음으로 건너뜀) 별도 이슈로 분리된다.

## 대안과 기각
- **캐시 정책 재사용**(전 단계 한 정책): 구현은 가장 쉽지만 보상이 달라 ICM 편향을 그대로 "TP-GTO"로 보이게 한다. 기각(CHARTER·RFC-08).
- **단계마다 별도 파일·인덱스 없이 이름 규칙만으로 조회**: 인덱스에 메타(run·LBR·λ)가 없으면 pill의 `modelLine`·재현성 기록이 안 된다. 기각.
- **정책을 한 파일에 단계별로 합치기**: 첫 로드가 커지고 3MiB 상한을 단계 수가 갉아먹는다. 기각.
- **새 `mode=export_tournament`**: 중복 위험(위 결정 2). 기각.

## 결과
- 이 ADR은 코드·`cloud.yml`·보호/하네스 경로를 바꾸지 않는다. ADR 0027의 F8 행은 H1–H4로 이어진다.
- 위험:
  - 단일 인원 정책이 3MiB 안이라는 것과 12MiB 합계는 가정이다(H4 첫 export에서 측정).
  - 인덱스 `schema_version` 2 승격이 `web/app/tpgto.js`·테스트의 정확한 `== 1` 비교를 깨뜨릴 수 있다(H1에서 grep·수정).
  - 단계 정의를 웹과 ADR 0027이 따로 가지므로 어긋날 수 있다(H2의 경계 테스트로 고정).
  - 생존자 수가 학습 인원과 다른 판(5인 버블 등)은 계속 "미학습"이다. 커버리지는 F10(7–9인)·단계 확장으로 넓힌다.

## 재검토 조건
- 첫 export 파일이 3MiB를 크게 넘거나 정책이 5개를 넘으면 결정 3(총량)을 다시 연다.
- 한 (env, stage, ante)에 정책을 둘 이상 서비스해야 하면(예: 등급별) 인덱스의 `ante` 아래 단계를 `tier`로 한 칸 더 나눈다(v3).
- 바운티·재진입을 지원하면 env_id 필드가 늘어 인덱스 키를 다시 정한다(ADR 0027 결정 1).
