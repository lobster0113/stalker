# STALKER 하네스 설계 (v0 — 2026-10-24)

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
L0  제품(STALKER) — 1) AI 실행·기록  2) 유형화  3) 학습 서비스  4) 시스템 점검·발전
                   └ README의 4)는 L1+L2가 구현한다
```

README가 강조한 대로 **L0의 1)·2)가 모든 것의 바닥**이다. 이유: 에이전트는 숫자로만 "좋아졌다"를 안다. 1)·2)가 신뢰할 수 있는 측정 신호를 내지 못하면 L1·L2는 노이즈 위에서 최적화(=퇴화)한다.

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

### 4.1 L0-1) AI 실행·기록
| 범주 | 지표 | 종류 |
|---|---|---|
| 엔진 정답성 | 칩 보존, 사이드팟/언콜드 벳 반환, 최소 레이즈·리오픈 규칙, 블라인드/앤티(클래식·BB앤티) 위반 0; 평가기 vs 참조 구현 일치 | 결정적, 속성기반 퍼징 |
| 기록 품질 | 스키마 검증 100%, 확률합=1, 재현성(같은 시드 → 같은 기록 해시) | 결정적 |
| AI 강도 ① | 고정 벤치마크 필드(nit/TAG/LAG/station/maniac/shove-fold 혼합) 대비 ROI, ICM $EV/토너먼트 (신뢰구간 포함) | 통계 |
| AI 강도 ② | **챔피언 리그**: 과거 머지된 AI 버전들과의 리그 Elo/ROI. 신버전은 현 챔피언을 유의하게 이겨야 챔피언 교체 | 통계 |
| AI 강도 ③ | 이론 앵커: HU/숏스택 push/fold 내시 대비 EV 손실, ICM 반영 콜링 레인지 대비 EV 손실 | 그라운드 트루스 |
| 적응력 | (적응형 AI − 사전정보 고정 AI)의 ROI 차이 = **정보 누적의 가치**; 상대 유형 식별까지 걸린 핸드 수 | 통계 (README 차별점의 직접 측정) |
| 비용 | 결정당 연산 시간, 토너먼트당 생성 시간 | 결정적 |

### 4.2 L0-2) 유형화
| 지표 | 의미 |
|---|---|
| 커버리지 | 분류 불가(`other`) 스팟 비율 |
| 표본 충분성 | 셀별 최소 표본 수 충족 비율 |
| 안정성 | 데이터 재생성/부트스트랩 시 유형별 결론(주 액션·빈도) 일치율 |
| **증류 충실도** | 유형화 결과만으로 만든 "룰북 봇"이 AI 대비 잃는 EV(bb/100) — 사람이 배울 수 있는 요약이 AI를 얼마나 재현하는가 |
| 압축도 | 룰 수/유형 수 (적을수록 학습 가능) — 충실도와의 파레토 |

### 4.3 L0-3) 학습 서비스 (후순위)
시뮬레이션 학습자(룰북만 보고 학습하는 봇)의 성능 향상, 퀴즈 정답률·EV손실 추이. 실사용자 생기면 사용 지표.

### 4.4 L2) 하네스 건강
| 지표 | 경보 조건 예 |
|---|---|
| 머지 처리량, PR 리드타임 | 7일 머지 0건 → 정체 |
| 머지 후 회귀/리버트율 | > 15% → 리뷰 품질 저하 |
| main 빨간불 시간 | > 0이면 P0 |
| 루틴 실패율·중단(타임아웃/권한 막힘) | 연속 3회 → 수리 모드 |
| 이슈 노화, 반복 실패 이슈 | 3회 실패 이슈 → 분해/재설계 |
| 리뷰어 놓친 결함 비율 | 머지 후 발견 버그 추적 |
| **지표 기울기** | 핵심 지표(챔피언 Elo, 증류 충실도)의 4주 기울기 ≈ 0 → 전략 재검토 이슈 |
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
| **Researcher** | 매주 / `research` 라벨 | 포커 AI 문헌(CFR 계열, 서브게임 해결, 상대 모델링, ICM/FGS) 조사 → `docs/research/` 노트 + 실행 가능한 이슈 | 구현 |
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

- **Phase 0 (사람과 함께 1회, 지금)**: 리포 생성, 하네스 골격(CLAUDE.md, CHARTER, 라벨, 이슈 템플릿, CI 게이트, referee-guard, metrics 파이프라인), 루틴 등록, 시드 백로그.
- **Phase 1 (자율)**: L0-1) 기반 — 토너먼트 엔진(설정 가능한 인원·스택·블라인드/앤티·페이아웃·멀티테이블), 기록 스키마, 벤치마크 봇 필드, ICM, 적응형 AI v0(상대 모델 + 에퀴티 + ICM), 이론 앵커(push/fold 내시).
- **Phase 2 (자율)**: L0-2) 스팟 택소노미, 유형화 리포트, 증류 충실도 측정.
- **Phase 3 (자율)**: AI 강화 연구 경로(CFR/서브게임 해결 + 상대 모델 기반 이탈), 챔피언 리그 본격 가동.
- **Phase 4 (자율)**: 학습 서비스.

---

## 9. 사람이 해야 하는 일 (부트스트랩 1회만)

자율 루프가 시작되기 전, 에이전트 권한으로는 불가능한 것만:
1. Claude GitHub App 설치(브라우저 OAuth) — 루틴이 리포를 클론·푸시·PR하기 위해 필요.
2. (필요시) 루틴 생성 승인.
그 외 리포 생성, 브랜치 보호, 라벨, Secret, 워크플로는 부트스트랩 세션이 `gh`로 수행한다.

## 10. 사용 목적과 배포 형태
- **개인 전용**: 외부 배포·상업화 없음 → GitHub 리포는 **private**.
- **학습 서비스(L0-3)는 휴대폰·태블릿·노트북 어디서나** 써야 한다 → 반응형 웹앱(모바일 우선, 오프라인 가능한 PWA 지향).
- 호스팅 1순위: **Claude Artifact**(기본 비공개, claude.ai 로그인만으로 모든 기기에서 접근, 학습 진도 같은 상태를 저장하는 런타임 기능 제공, 에이전트가 재발행으로 갱신 가능). 2순위: 접근 제어가 걸린 정적 호스팅. 최종 선택은 Phase 4 착수 시 ADR로 기록.
- 서비스 데이터(유형화 결과·문제 은행)는 L0-2)의 산출물을 빌드 시 정적으로 묶어 넣는다 → 서비스는 무거운 연산 없이 동작.

## 11. 알려진 제약·리스크
- 루틴 사용량은 구독 한도를 공유한다 → 주기 설계는 한도 내에서, L2가 비용 대비 성과로 조정.
- private 리포의 GitHub Actions 분(minute)은 월 한도가 있다 → CI는 빠른 결정적 게이트 + 작은 평가만, 대규모 시뮬레이션은 루틴 클라우드 VM에서 배치로 돌리고 결과 요약과 재현 정보(시드·커밋)를 기록. 홀드아웃 평가는 Actions에서 작게·자주 대신 크게·드물게(일 1회).
- 모든 루틴이 같은 GitHub 앱 신원으로 동작 → Builder/Reviewer 분리는 권한이 아니라 **절차 + 사후 감사**로 강제된다.
- 루틴 GitHub 이벤트는 시간당 상한 초과 시 유실 → Reviewer는 정기 스윕도 겸한다.
- "세계급"은 봇 상대 ROI로 증명되지 않는다 → 이론 앵커·챔피언 리그·(장기) 외부 벤치마크가 필요.

## 참고
- https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents
- https://www.anthropic.com/engineering/harness-design-long-running-apps
- https://openai.com/index/harness-engineering/
- https://martinfowler.com/articles/harness-engineering.html
- https://www.humanlayer.dev/blog/skill-issue-harness-engineering-for-coding-agents
- https://arxiv.org/abs/2505.22954 (Darwin Gödel Machine)
- https://arxiv.org/abs/2604.25850 (Agentic Harness Engineering)
- https://code.claude.com/docs/en/routines.md , https://code.claude.com/docs/en/github-actions.md
