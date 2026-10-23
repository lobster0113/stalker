# ADR 0001: 자율 에이전트 하네스로 개발한다

- 상태: 채택 (2026-10-24, 부트스트랩 세션)
- 맥락: 사용자는 개발·GitHub 관리에 일절 관여하지 않는다. 시스템은 PR을 끝없이 반복하며 발전해야 하고, 하네스 자체의 운영·성공 여부도 하네스가 다룬다.
- 결정:
  1. Claude Code 클라우드 루틴(Builder/Reviewer/Planner/Researcher/Gardener/Auditor)이 GitHub private 리포를 운영한다.
  2. 결정적 판정은 GitHub Actions(CI)가, 운영 데이터는 `ops` 브랜치가 담당한다.
  3. 심판(`referee/`, 헌장)은 보호 경로이며 별도 절차로만 수정된다.
  4. 실효 주기는 `harness/schedule.json`(리포 내부)로 통제해 L2가 PR로 조정할 수 있게 한다.
  5. 학습 서비스는 개인 전용, 다기기 접근(1순위 Claude Artifact).
- 결과: 근거는 `docs/HARNESS_DESIGN.md`. Builder/Reviewer는 같은 GitHub 앱 신원으로 동작하므로 역할 분리는 절차 + Auditor 사후 감사로 보장한다.
