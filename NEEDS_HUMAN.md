# 사람이 결정해야 하는 항목 (harness/PROTOCOL.md §9 예외)

## NH-1 AI 개발 연산 자원·예산
- 상태: resolved (2026-10-27) — 사용자 결정: **월 예산 상한 $100**(린 시나리오). RunPod 선불 크레딧 $100 충전(자동 충전 꺼짐), Secret `RUNPOD_API_KEY` 등록(2026-10-26T16:10:59Z). 표준 승격은 D2 비용 재산정 후 다시 묻는다 — 결정 패키지 `docs/decisions/0004-ai-compute-plan-proposal.md`
- 추천: 린(월 약 12만~17만원)으로 시작 → 파이프라인 안정 후 표준(월 약 93만~123만원) 승격
- 사용자 조치: 예산 상한 결정, RunPod 가입·크레딧·API 키 Secret 등록, (표준 시) CPU 서버
- 막히는 이슈: RL 학습(M2), 대규모 Gate 판정

## NH-2 ICMizer PRO 구독·자격증명·요청 형식 캡처
- 상태: resolved — 불필요 (2026-10-27, ADR 0008: Gate A 은퇴). 결제하지 않아도 된다
- 사용자 조치: PRO 결제($32.99/월 또는 $179.99/년), `ICMIZER_EMAIL`/`ICMIZER_PASSWORD` Secret 등록, 대화 세션에서 1회 트래픽 캡처
- 막히는 이슈: #18

## NH-3 D1 데모 체험 피드백 (비차단)
- 상태: open (2026-10-27)
- 필요 이유: UI·UX 품질은 결정적 센서로 다 잡히지 않는다(헌장 7, Gate U)
- 사용자 조치: 게시본 https://claude.ai/artifact/LpQTDzYgZgTjcY5T4BwcZb 을 써 보고 수정 요청을 대화 세션에 말하기. 대화 세션이 이슈로 바꾼다
- 사용자 반응(2026-10-27): "전반적으로 괜찮음, 데모로 훌륭함, 나중에 수정 요청 예정"
- 막히는 이슈: 없음
