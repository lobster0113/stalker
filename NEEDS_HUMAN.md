# 사람이 결정해야 하는 항목 (harness/PROTOCOL.md §9 예외)

## NH-1 AI 개발 연산 자원·예산 (결정 예정: 2026-10-25 아침)
- 상태: open — 결정 패키지 `docs/decisions/0004-ai-compute-plan-proposal.md`
- 추천: 린(월 약 12만~17만원)으로 시작 → 파이프라인 안정 후 표준(월 약 93만~123만원) 승격
- 사용자 조치: 예산 상한 결정, RunPod 가입·크레딧·API 키 Secret 등록, (표준 시) CPU 서버
- 막히는 이슈: RL 학습(M2), 대규모 Gate 판정

## NH-2 ICMizer PRO 구독·자격증명·요청 형식 캡처 (필수, 사용자 결정 2026-10-24: 자동화·약관 위험 수용)
- 상태: open
- 사용자 조치: PRO 결제($32.99/월 또는 $179.99/년), `ICMIZER_EMAIL`/`ICMIZER_PASSWORD` Secret 등록, 대화 세션에서 1회 트래픽 캡처
- 막히는 이슈: #18
