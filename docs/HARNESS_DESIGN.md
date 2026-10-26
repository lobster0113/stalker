# STALKER 하네스 설계 (v1 — 2026-10-27, 방향 전환 ADR 0008 반영)

> 이 문서는 사람 개입 없이 AI 에이전트가 STALKER 시스템을 무한히 발전시키기 위한 **하네스(harness)** 의 설계다.
> 하네스 자신(어떻게 굴리는지, 잘 굴러가는지)도 이 하네스가 다루고 발전시키는 대상이다.

---

## 1. 연구 요약: 하네스 엔지니어링에서 가져올 것

| 출처 | 핵심 교훈 | STALKER 적용 |
|---|---|---|
| Anthropic, *Effective harnesses for long-running agents* (2025-11) | 세션은 기억이 없다. 상태는 **파일·git·기능 목록(pass/fail)** 으로 넘긴다. 세션당 한 기능, 시작 시 "아직 잘 돌아가는지" 확인, 끝날 때 커밋. | GitHub Issues = 작업 큐, `harness/STATE.md` = 인수인계, 시작 시 smoke 게이트 |
| Anthropic, *Harness design for long-running apps* | **생성자와 평가자를 분리**하라. 자기 작업을 자기가 평가하면 관대해진다. 작업 전 "완료 기준 계약(sprint contract)". 하네스의 모든 부품은 "모델이 혼자 못한다"는 가정이며 주기적으로 재검증해 걷어내야 한다. | Builder ≠ Reviewer(회의적 프롬프트). 이슈마다 수용 기준. 메타 감사가 하네스 부품의 필요성 재검증 |
| OpenAI, *Harness engineering* (Codex, 2026) | AGENTS.md는 백과사전이 아니라 **목차(~100줄)**, `docs/`가 기록 시스템. 규칙은 **기계적으로 강제**(린터·테스트, 오류 메시지에 고치는 법). 엔트로피는 **주기적 가비지 컬렉션 에이전트**가 치운다. | 짧은 `CLAUDE.md` + `docs/`. 게이트 실패 메시지는 수정 지침 포함. 주간 Gardener |
| Thoughtworks/Fowler, *Harness engineering* | **Guide(사전 유도)** 와 **Sensor(사후 감지)** 를 모두. 결정적(computational) 센서는 매 변경마다, 추론적(LLM 리뷰) 센서는 비싸니 선별적으로. 행동(정답성) 하네스가 가장 어렵다. | 결정적 게이트(CI) 우선, LLM 리뷰는 보조. 포커는 이론적 정답 앵커가 있는 영역부터 센서화 |
| HumanLayer, *Skill issue* | 성공은 조용히, 실패만 시끄럽게(컨텍스트 보호). 서브에이전트는 역할극이 아니라 **컨텍스트 격리**용. 과설계 금지, 실제 실패가 생길 때 하네스를 키워라. | 게이트 출력 요약형. 시작은 최소 하네스, 실패 로그 기반으로 확장 |
| Darwin Gödel Machine / 자기개선 하네스 연구 (2025-26) | 자기수정 + **경험적 검증** + 아카이브(계보)로 개선 가능. 단 **목표 해킹**(평가 신호를 조작해 점수만 올림) 사례가 관찰됨. | **심판(referee) 보호**가 설계의 1원칙. 수치는 에이전트가 아니라 CI가 산출. 홀드아웃 시드는 에이전트가 볼 수 없는 GitHub Secret |
| Agentic Harness Engineering (관측 기반 하네스 진화) | 실행 → 관측(트레이스) → 분석 → 가설 → 수정 → 평가의 루프로 하네스 자체를 진화. | L2 메타 루프: 하네스 변경은 **가설+측정창이 있는 실험**으로만, 효과 없으면 자동 롤백 |

---

## 2. 3층 구조

```
L2  메타 하네스   — "하네스가 잘 돌고 있는가?"를 측정하고, 하네스 자체를 실험적으로 개선
L1  개발 하네스   — 에이전트들이 이슈 → 브랜치 → PR → 리뷰 → 머지로 L0를 개선
L0  제품(STALKER) — ① 시뮬레이터(캐시·토너먼트)  ② TP 명세  ③ TP-GTO AI·페르소나 AI
                   ④ 학습 서비스(Training Game · 학습 섹션 · 복기용 Training Game)
```

**L0의 ①·②가 모든 것의 바닥**이다. 시뮬레이터가 틀리면 학습이 무의미하고(헌장 6), TP 명세가 흔들리면 AI·채점·UI가 서로 다른 것을 가리킨다. 에이전트는 숫자로만 "좋아졌다"를 알기 때문에, 이 둘이 신뢰할 수 있는 측정 신호를 내지 못하면 L1·L2는 노이즈 위에서 최적화(=퇴화)한다.

---

## 3. 1원칙: 심판은 선수가 아니다 (Referee Integrity)

자율 자기개선 시스템의 가장 큰 실패 모드는 **Goodhart** — 평가를 바꾸거나 평가에 과적합해서 점수만 오르는 것이다.

1. **수치의 출처는 CI뿐.** 성능·품질 수치는 GitHub Actions가 계산해 PR 체크/코멘트로 남긴다. 에이전트가 PR 본문에 쓴 수치는 근거로 인정하지 않는다.
2. **보호 경로(`referee/`)**: 평가 코드, 벤치마크 상대(봇 필드·챔피언 아카이브), 지표 정의, 헌장(`docs/CHARTER.md`).
   - 일반 PR은 보호 경로를 수정할 수 없다(CI `referee-guard` 체크가 실패시킴).
   - 보호 경로 변경은 `referee-change` 라벨 + 별도 **Referee Reviewer** 루틴의 승인 + "구 지표와 신 지표 병행 산출" 증거가 필요하다.
3. **홀드아웃 평가**: 공개 시드 평가(에이전트가 로컬에서 돌릴 수 있음)와 별도로, GitHub Secret의 시드로 도는 홀드아웃 평가를 CI가 수행한다. 두 결과가 벌어지면(과적합 신호) L2가 경보를 낸다.
4. **이론 앵커**: 봇 상대 ROI는 상대 봇에 과적합될 수 있다. 정답이 계산 가능한 영역(숏스택 push/fold 내시 균형, ICM 계산, 핸드 평가)을 **그라운드 트루스 센서**로 둔다.
5. **감사 가능성**: 모든 머지는 (a) 해당 head SHA의 CI 통과, (b) Reviewer 판정 코멘트를 가져야 한다. 메타 감사가 위반을 사후 검출한다.

---

## 4. 측정 체계 (센서)

### 4.1 L0-① 시뮬레이터
| 범주 | 지표 | 종류 |
|---|---|---|
| 규칙 정답성 | Gate R(독립 규칙 모델 대조) 100% — 토너먼트 + 캐시게임 | 결정적 |
| 재현성 | 같은 시드 → 같은 기록 해시 | 결정적 |
| 처리량 | 핸드/초(엔진 단독, 정책 포함) | 측정 |

### 4.2 L0-②③ TP·AI
| 지표 | 의미 |
|---|---|
| Gate T | 행동이 TP만 거치는가, 계산 항목이 정의와 일치하는가 |
| Gate S | 유형 버킷 안 섭동에 둔감한가, 경계 절벽이 없는가 |
| Gate Q | 페르소나 필드 대비 bb/100·ROI, 이론 앵커 EV 손실, 복잡성 비용 |
| Gate F | 사람 수준 TP 오차를 넣어도 이기는가(따라 할 수 있는가) |
| Gate L | 게임 내 공개 정보만 쓰는가 |
| 페르소나 충실도 | 난이도별 페르소나의 VPIP·PFR·공격성이 목표 프로필과 맞는가 |

### 4.3 L0-④ 학습 서비스
| 지표 | 의미 |
|---|---|
| Gate U | E2E 흐름, 3종 화면 스크린샷, 성능 예산, 접근성 |
| 시각 품질 | Reviewer의 스크린샷 판단(추론적 센서, UI PR마다) |
| Gate E | 시뮬레이션 학습자의 향상폭(D4 이후) |
| 실사용 | 사용자 본인의 TP 오차 추이(데이터가 생기면) |

### 4.4 L2) 하네스 건강
| 지표 | 경보 조건 예 |
|---|---|
| 머지 처리량, PR 리드타임 | 7일 머지 0건 → 정체 |
| 머지 후 회귀/리버트율 | > 15% → 리뷰 품질 저하 |
| main 빨간불 시간 | > 0이면 P0 |
| 루틴 실패율·중단(타임아웃/권한 막힘) | 연속 3회 → 수리 모드 |
| 이슈 노화, 반복 실패 이슈 | 3회 실패 이슈 → 분해/재설계 |
| 리뷰어 놓친 결함 비율 | 머지 후 발견 버그 추적 |
| **지표 기울기** | 핵심 지표(Gate Q 강도, Gate S 둔감성, Gate F 따라 하기)의 4주 기울기 ≈ 0 → 전략 재검토 이슈 |
| 공개/홀드아웃 괴리 | 과적합 경보 |
| 비용 대비 성과 | 머지 PR당·지표 상승당 사용량 |
| 문서 신선도 | 코드와 불일치하는 docs 링크/명령 |

---

## 5. 에이전트 로스터 (Claude 루틴)

모든 에이전트는 Claude Code **루틴(scheduled cloud agents)** 으로 클라우드에서 실행된다(사용자 PC 불필요). 결정적 게이트·평가는 **GitHub Actions**에서 돈다.

| 루틴 | 트리거 | 하는 일 | 할 수 없는 일 |
|---|---|---|---|
| **Builder** | 2시간마다 | ① 내 PR에 변경요청 있으면 그것부터 ② `ready` 이슈 최상위 1개 집어 `in-progress` 표시 → 구현 → 로컬 게이트 → PR(수용 기준 체크리스트 포함) | 머지, `referee/` 수정, 라벨 `referee-change` 부여 |
| **Reviewer** | PR opened/synchronize (GitHub 이벤트) | 회의적 리뷰: 수용 기준 충족, CI 수치, 테스트 실효성, 범위 이탈. 판정 `MERGE`/`CHANGES`/`CLOSE` 코멘트(head SHA 명시). MERGE면 `gh pr merge --auto --squash` | 코드 직접 수정 |
| **Planner** | 매일 | `metrics/`·STATE·로드맵 읽고 이슈 생성/우선순위(각 이슈에 수용 기준 = 계약). `ready` 큐 3~8개 유지. 3회 실패 이슈 분해 | 구현 |
| **Gardener** | 매주 | 엔트로피 청소: 죽은 코드, 문서-코드 불일치, 중복, 느린 테스트 | 기능 추가 |
| **Researcher** | 매주 / `research` 라벨 | 포커 이론·AI 문헌(CFR 계열, 개념 병목·해석 가능 정책, 상대 모델링, ICM), 학습 과학·UX 조사 → `docs/research/` 노트 + 실행 가능한 이슈 | 구현 |
| **Harness Auditor (L2)** | 매주 | 하네스 건강 리포트(`harness/reports/`), 위반 감사(심판 무결성, 머지 절차), 하네스 실험 제안·판정·롤백 | 제품 코드 수정 |
| **Referee Reviewer** | `referee-change` 라벨 PR | 심판 변경의 정당성·연속성 검증 | 일반 PR 리뷰 |

동시성: 초기엔 Builder 1개만(충돌 방지). L2가 처리량 병목을 확인하면 영역별(Builder-P1, Builder-P2) 병렬화를 **실험으로** 도입한다.

---

## 6. 상태와 기억 (세션 간 인수인계)

| 저장소 | 내용 | 쓰는 주체 |
|---|---|---|
| GitHub Issues + 라벨 | 작업 큐. `ready`/`in-progress`/`blocked`, `P0..P3`, `area:engine/ai/records/typing/service/harness`, `kind:experiment` | Planner, Builder |
| `CLAUDE.md` (~100줄) | 목차 + 절대 규칙 + 루틴별 진입점 | L2만 PR로 수정 |
| `docs/CHARTER.md` | 북극성·불변 목표(README에서 파생). **보호 경로** | Referee 절차 |
| `docs/` | 아키텍처, ADR(`docs/decisions/`), 리서치 노트 | 모두 |
| `ops:STATE.md` | 현재 초점, 진행 중 실험, 최근 경보 | Planner, Auditor |
| `ops:journal/` | 루틴 실행 기록(outcome, friction) — L2의 관측 원천 | 모든 루틴 |
| `harness/experiments/` | 하네스 실험 기록(가설·변경·측정창·판정) | Auditor |
| `ops:metrics/history.jsonl` | 지표 시계열 (CI가 main 머지마다 append) | **CI만** |
| `referee/champions/` | 역대 챔피언 AI 스냅샷 | CI(승급 시) |

`ops` 브랜치는 리뷰 없는 운영 데이터 전용이다(코드 없음). 상세 규칙은 `harness/PROTOCOL.md`.

---

## 7. 루프

### 7.1 L1 개발 루프
```
Planner: 지표·로드맵 → 이슈(수용 기준) ─┐
                                        ▼
Builder: 이슈 집기 → 구현 → 로컬 게이트(빠름) → PR
                                        ▼
CI: 결정적 게이트 + 공개 평가 + 홀드아웃 평가 + referee-guard → 체크/코멘트
                                        ▼
Reviewer: 계약·CI 수치 확인 → MERGE(auto-merge) / CHANGES / CLOSE
                                        ▼
main 머지 → CI: metrics/history 갱신, 챔피언 도전전 → 승급/유지
```
**게이트 등급**: `G0` 테스트·린트·스키마 (항상) / `G1` 엔진 퍼징·재현성 (항상) / `G2` AI 강도 비회귀 — 성능 영향 경로 변경 시 / `G3` 챔피언 도전 — main 머지 후.

### 7.2 L2 메타 루프 (하네스가 하네스를 발전)
```
관측: 루틴 실행 결과, PR/CI 이력, 지표 시계열, 비용
 → 진단: 4.4 경보 규칙
 → 가설: "Reviewer 프롬프트에 X를 넣으면 리버트율이 줄 것"
 → 실험 PR (kind:experiment, harness/experiments/NNN.md에 측정창·성공기준 명시)
 → 측정창 경과 후 판정: 유지 / 롤백(자동 PR)
```
하네스 부품은 "모델이 혼자 못하는 것"에 대한 가정이다. Auditor는 분기마다 부품 하나를 끄는 **제거 실험**도 수행해 불필요한 부품을 걷어낸다.

### 7.3 안전장치
- **킬 스위치**: `harness/PAUSE` 파일이 있으면 모든 루틴은 즉시 종료(상태 보고만).
- **회로 차단기**: main CI 실패 → P0 이슈 자동 생성, Builder는 P0 외 작업 금지. 머지 후 G3에서 유의한 회귀 → 자동 리버트 PR.
- **처리 한도**: 열린 Builder PR ≤ 2, 루틴 1회 실행 시간 상한, 사용량 한도 근접 시 Planner가 주기 축소.
- **비가역 행동 금지 목록**: 리포 삭제·강제 푸시·히스토리 재작성·secret 변경·브랜치 보호 해제·외부 서비스 게시.

---

## 8. 로드맵 (부트스트랩 이후는 하네스가 스스로 갱신)

- **Phase 0 부트스트랩 (완료, 2026-10-24)**, 구 로드맵 P0~P2 (2026-10-24~26, ICMizer 기준 토너먼트 AI — ADR 0008로 중단, 엔진·Gate R·L 등은 재사용).
- 아래 D0~D4는 사용자의 개발 계획(`docs/ORIGIN.md` "개발 계획")을 따른다.

| 단계 | 내용 | 종료 기준 |
|---|---|---|
| D0 방향 전환 | 헌장·TP v0·게이트·로드맵·하네스 지침 개정 | 이 문서 머지 |
| D1 데모 사이트 | AI 없이 흐름을 보여주는 웹(`web/`): Training Game(테이블 중앙·TP 패널 오른쪽, 설정 1/1-1/1-2/2, 다른 플레이어 1.5초 진행, TP 입력→모의 채점→약점 기록→학습 섹션 추천), 학습 섹션(항목별 쉬움/보통/어려움), 복기 입력. 어두운 톤, 실제 포커 클라이언트 수준의 테이블 그래픽, 장면 전환·칩·카드 애니메이션. 모의 데이터는 `web/` 안의 고정 JSON | Gate U 통과, 3종 화면에서 전 흐름 체험 가능, 단일 HTML 빌드 산출(Artifact 게시용), 사용자 체험 피드백 요청(NEEDS_HUMAN, 비차단) |
| D2 설계·준비 | TP v1 확정(조사·판별력), TP-GTO 학습 설계 채택(ADR 0009), 예상 비용 산정(ADR 0004 개정 → NEEDS_HUMAN), 시뮬레이터 캐시게임 확장 + Gate R 확장 + 처리량 목표, 페르소나 AI 1~19(규칙 기반), 게이트 T·S·Q·F 구현과 판별력 확인 | Gate R 100%(캐시·토너먼트), 게이트 판별력 확인, 설계 ADR 채택 |
| D3 학습 | 첫 환경(6max 캐시 100BB, 9인 SNG)에서 TP-GTO 등급별 학습 → 게이트 판정. 웹에 실제 채점 연결(사전계산 데이터) | 첫 환경에서 레벨 1 |
| D4 서비스 완성 | 학습 섹션 문제 생성(TP-GTO 기반), 복기 → 유사 상황 생성, 약점 추천 고도화, 환경 확장, Gate E | 레벨 2 |

- 단계 전환은 Planner가 STATE에 기록한다. D1과 D2는 겹칠 수 있다(D2의 시뮬레이터·TP 조사는 D1 UI 작업과 충돌하지 않음). 다만 D1이 끝나기 전에는 D1 이슈가 우선이다.
- D2의 시뮬레이터 작업은 "잘못 만들면 이후 학습이 전부 무의미"(원문)하므로 규칙 변경 PR마다 Gate R 검사 추가를 필수로 하고, Reviewer가 규칙 명세와 대조한다.

## 9. 사람이 해야 하는 일 (부트스트랩 1회만)

자율 루프가 시작되기 전, 에이전트 권한으로는 불가능한 것만:
1. Claude GitHub App 설치(브라우저 OAuth) — 루틴이 리포를 클론·푸시·PR하기 위해 필요.
2. (필요시) 루틴 생성 승인.
그 외 리포 생성, 브랜치 보호, 라벨, Secret, 워크플로는 부트스트랩 세션이 `gh`로 수행한다.

## 10. 사용 목적과 배포 형태
- **개인 전용**: 외부 배포·상업화 없음. 단 GitHub 리포는 **public**(사용자 결정, 2026-10-24). 공개 리포이므로 외부 입력은 신뢰하지 않는다(`harness/PROTOCOL.md` §8, 상호작용 제한 collaborators_only — 2027-04-23 만료).
- **학습 서비스는 휴대폰·태블릿·노트북 어디서나** 써야 한다 → 반응형 웹앱(모바일 우선). 폰은 세로 화면에서 테이블 위·TP 패널 아래(바텀 시트), 태블릿 가로·노트북은 테이블 중앙·TP 패널 오른쪽.
- 코드 위치: `web/`. 빌드 산출물은 **단일 HTML 파일**로도 만들 수 있어야 한다(외부 CDN 의존 없이) — 사용자에게 보여줄 때 대화 세션이 Claude Artifact(기본 비공개)로 게시한다. GitHub Pages 같은 공개 호스팅은 쓰지 않는다.
- 서비스 데이터(TP-GTO 정답·문제 은행)는 빌드 시 정적으로 묶는다 → 서비스는 무거운 연산 없이 동작. 학습 기록(약점)은 기기 로컬 저장 + Artifact 저장 기능(가능하면).

## 11. 알려진 제약·리스크
- 루틴 사용량은 구독 한도를 공유한다 → 주기 설계는 한도 내에서, L2가 비용 대비 성과로 조정.
- private 리포의 GitHub Actions 분(minute)은 월 한도가 있다 → CI는 빠른 결정적 게이트 + 작은 평가만, 대규모 시뮬레이션은 루틴 클라우드 VM에서 배치로 돌리고 결과 요약과 재현 정보(시드·커밋)를 기록. 홀드아웃 평가는 Actions에서 작게·자주 대신 크게·드물게(일 1회).
- 모든 루틴이 같은 GitHub 앱 신원으로 동작 → Builder/Reviewer 분리는 권한이 아니라 **절차 + 사후 감사**로 강제된다.
- 루틴 GitHub 이벤트는 시간당 상한 초과 시 유실 → Reviewer는 정기 스윕도 겸한다.
- "따라 할 수 있다"는 봇 상대 강도만으로 증명되지 않는다 → Gate F(사람 수준 오차 주입)와 Gate E(시뮬레이션 학습자), 장기적으로 사용자 본인의 오차 추이가 필요하다.
- UI 품질은 결정적 센서로 다 잡히지 않는다 → 스크린샷 기반 Reviewer 판단과 사용자 체험 피드백(NEEDS_HUMAN)을 함께 쓴다.

## 참고
- https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents
- https://www.anthropic.com/engineering/harness-design-long-running-apps
- https://openai.com/index/harness-engineering/
- https://martinfowler.com/articles/harness-engineering.html
- https://www.humanlayer.dev/blog/skill-issue-harness-engineering-for-coding-agents
- https://arxiv.org/abs/2505.22954 (Darwin Gödel Machine)
- https://arxiv.org/abs/2604.25850 (Agentic Harness Engineering)
- https://code.claude.com/docs/en/routines.md , https://code.claude.com/docs/en/github-actions.md
