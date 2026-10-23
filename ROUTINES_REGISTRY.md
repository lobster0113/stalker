# 루틴 등록 현황 (부트스트랩 세션이 기록)
| 역할 | 트리거 ID | 고정 트리거 | 등록일 |
|---|---|---|---|
| builder | trig_011eAx9HtqKQiiDEYG2uAFuS | cron `0 * * * *` (UTC), opus-5.5 | 2026-10-24 |
| reviewer | trig_01Ngm2AeBPCVHfLAaUfgMHAn | cron `30 * * * *` + GitHub PR opened/synchronize/reopened (webhook 855db140-fa9f-4d16-a894-16ab933e331b), opus-5.5 | 2026-10-24 |
| planner | trig_01PeXvjPCd8wAQByCuZEEECN | cron `0 21 * * *` (06:00 KST), opus-5.5 | 2026-10-24 |
| researcher | trig_01P8Ave4Fb6zbimdsc2A6MtH | cron `0 0 * * 2` (화 09:00 KST), sonnet-5.5 | 2026-10-24 |
| gardener | trig_01XBXWsTMYMuCDNdBhECqiG4 | cron `0 0 * * 4` (목 09:00 KST), sonnet-5.5 | 2026-10-24 |
| auditor | trig_01UVf8HV7vXyzfMbP1iuD5he | cron `0 0 * * 0` (일 09:00 KST), opus-5.5 | 2026-10-24 |

모든 루틴: 환경 Default(env_015kAjb2fxUeJqoNATPJFQXS), MCP 커넥터 없음(개인 Gmail/Drive 등 접근 차단).
루틴 설정 자체(모델·고정 트리거)는 에이전트가 바꿀 수 없다. 실효 주기는 main의 harness/schedule.json으로 조정한다.
