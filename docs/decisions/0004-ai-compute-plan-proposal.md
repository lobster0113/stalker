# ADR 0004 (제안): AI 개발 착수 — 연산 자원·예산·사용자 조치

- 상태: **제안 — 사용자 결정 대기** (2026-10-25 아침). 결정되면 "채택"으로 바꾸고 선택안을 기록한다.
- 근거: 비용 조사(2026-10-24, 출처는 하단), 로컬 측정, ADR 0003, `referee/GATES.md`.

## 1. 결론 (추천)
**단계적 착수: 1~3주차 "린(Lean)" → 파이프라인 안정 후 "표준(Standard)"으로 승격.**
공개된 RL 포커 에이전트(AlphaHoldem: 860만 파라미터, 8 GPU·64코어 서버로 3일 / VRPO 2026: RTX 5090 4장으로 63시간)는 모두 "표준" 규모 안에 들어온다.
세계급까지 가는 길에서 돈보다 먼저 막히는 것은 **시뮬레이터 속도**다 → 첫 투자는 Rust 고속 엔진·ICM·에퀴티(#19)에 한다.

## 2. 측정·사실
| 항목 | 값 | 출처 |
|---|---|---|
| 사용자 PC | Intel Core 5 120U(저전력 10코어), RAM 16GB, GeForce MX570 4GB | 로컬 확인 → **학습용으로 부적합, 클라우드 전제** |
| PokerKit(파이썬) 무작위 플레이 | 9인 약 143핸드/초/코어, 6인 약 177 | 로컬 측정(2026-10-24) |
| 우리 평가기 / MC 에퀴티 | 27만 평가/초, 3인 4만 시뮬/초 | 로컬 측정 |
| Rust 엔진(추정) | 무작위 10⁵~10⁶핸드/초/코어, 신경망 포함 시 50~150핸드/초/스레드 | 추정 — #19에서 실측 |
| 필요 학습 규모(가정) | 본 실험 1회 ≈ 10억 샘플, 제거 실험 1~2억 | AlphaHoldem 27억 핸드, VRPO 15억 스텝 |
| 게이트 판정 1회 | 군당 1.5만~2.2만 토너먼트(검정력 0.9 사전 등록 시 더 많음) | 검토 문서 §2.5 |

## 3. 예산 시나리오 (월, 1 USD ≈ 1,325원)
| | 린 (추천 시작) | 표준 (추천 승격) | 공격적 |
|---|---|---|---|
| 구성 | RunPod GPU(RTX 4090 커뮤니티 $0.34/h) 월 100시간 + 64코어 스팟 CPU(GCP n2d $0.49/h 등) 월 100시간 | 64~96스레드 CPU 상시(Hetzner AX162 €614/월, 또는 AWS c8g 스팟 ≈$478) + RTX 5090 월 300시간(≈$207) | 128~192스레드 + RTX 5090 4장 상시 |
| 월 비용 | **약 $90~130 ≈ 12만~17만원** | **약 $700~930 ≈ 93만~123만원** (+Hetzner 설치비 약 47만원 1회) | 약 $3,000~3,500 ≈ 400만~470만원 |
| 가능한 것 | 시스템 구축·제거 실험, 본 학습 주 1회 미만, 판정 1회 수십 분~수 시간 | 본 학습 주 2~4회, 판정 1회 수 분, 하루 수백만 토너먼트 시뮬 | 리그·집단 학습, 본 학습 주 10회+ |
| 그 외 고정비 | ICMizer PRO $32.99/월(또는 연 $179.99) — 모든 시나리오 공통. Claude Max 5x(기존). | 동일 | 동일 |

3개월 합계(대략): 린 약 50만원 / 표준 약 300만~420만원 / 공격적 약 1,200만~1,400만원 (+ICMizer).

## 4. 사용자가 해야 할 일 (결정 후 1회)
| # | 할 일 | 소요 | 이유 |
|---|---|---|---|
| 1 | **예산 상한 결정**(시나리오 + 월 최대 금액) | 5분 | 에이전트가 넘지 못하는 하드 상한으로 코드화 |
| 2 | **RunPod 가입·결제·크레딧 충전**(예: $50~100), API 키 발급 → 터미널에서 `! gh secret set RUNPOD_API_KEY -R lobster0113/stalker` (키는 사용자만 입력) | 15분 | GPU/CPU 작업 실행. 키는 GitHub Secret에만 존재, 에이전트는 못 봄 |
| 3 | **ICMizer PRO 결제** → `! gh secret set ICMIZER_EMAIL ...`, `! gh secret set ICMIZER_PASSWORD ...` | 10분 | Gate A 기준선(#18) |
| 4 | **ICMizer 요청 형식 1회 캡처 세션**(이 대화에서 함께, 브라우저 버전 사용) | 20~30분 | 자동 클라이언트 구현 근거 |
| 5 | (표준 승격 시) Hetzner 가입·본인확인·AX162 주문, 또는 AWS/GCP 계정 | 30분~1일(심사) | 상시 CPU 서버 |

## 5. 하네스 측 안전장치 (사용자 개입 없이 돈을 쓰는 구조이므로)
- 클라우드 작업은 **CI의 런처 워크플로만** 실행한다(키는 Secret, 에이전트는 작업 명세 파일만 PR로 제출).
- 런처는 실행 전 예산 원장(`ops:budget/ledger.jsonl`)을 확인해 월 상한 초과 작업을 거부하고, 작업마다 최대 시간을 강제하며, 끝나면 인스턴스를 반드시 종료한다(고아 인스턴스 감시 일 1회).
- RunPod 계정 자체의 지출 한도/선불 크레딧으로 이중 상한.
- 지출 내역은 Auditor 주간 리포트의 필수 항목.

## 6. 일정 (결정 즉시 시작 시)
| 시기 | 내용 |
|---|---|
| ~10/31 (M1) | 시뮬레이션·참조기·기록·유형화 v0·학습 페이지 프로토타입 (연산 비용 거의 0) |
| 11/1~11/14 (M2) | Rust 고속 엔진·ICM·에퀴티, ICMizer 클라이언트, RL 학습 파이프라인 + 첫 소규모 학습(린) |
| 11월 중순~ | 처리량 실측 후 표준 승격 여부 재결정 → Gate C(기억 효과)·Gate A/B 첫 측정 |

## 출처
AlphaHoldem(AAAI 2022) https://ojs.aaai.org/index.php/AAAI/article/view/20394/20153 · VRPO https://arxiv.org/pdf/2605.19235 · Pluribus https://syncedreview.com/2019/07/11/an-absolute-monster-bluffer-facebook-cmu-ai-bot-beats-poker-pros/amp/ · SpinGPT https://arxiv.org/pdf/2509.22387v2 · RunPod https://www.runpod.io/pricing · Lambda https://lambda.ai/pricing · Hetzner AX162 https://www.hetzner.com/dedicated-rootserver/ax162/ · AWS c8g https://calculator.holori.com/aws/ec2/c8g.16xlarge/us-east-1 · GCP n2d https://calculator.holori.com/gcp/vm/n2d-highcpu-64 · ICMizer 가격 https://www.icmizer.com/icmizer/pricing/ , 클라우드 계산 https://www.icmizer.com/en/blog/icm-to-fgs-future-game-simulations/ · PokerKit 벤치 https://arxiv.org/pdf/2308.07327 · 환율 https://www.valutafx.com/history/krw-usd-2026
가격은 2026년 9~10월 기준이며 스팟 가격은 매일 변동한다. Rust 엔진 처리량과 학습 샘플 처리량은 추정치이며 M2에서 실측한다.
