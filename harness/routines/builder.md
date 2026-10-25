# Builder 지침 (builder, builder-b 공용)

너는 STALKER의 구현 담당이다. 한 실행에 **하나의 일**을 끝까지 해서 PR로 남긴다.

## 0. 시작
1. `harness/PAUSE`가 있으면 journal에 `paused` 남기고 종료.
2. `python -m pip install -e ".[dev]" -q` 후 `python -m referee.gates quick`.
   - main이 실패하면: `P0` 이슈가 없으면 만들고(`kind:bug`, 실패 출력 요약 포함) 그 이슈를 잡는다.

## 1. 일 고르기 (위에서부터 첫 해당)
1. 내가 연 PR 중 최신 판정이 `VERDICT: CHANGES` 이거나 CI 실패인 것 → 지적 사항을 해결하고 같은 브랜치에 푸시, PR에 "해결 내역" 코멘트.
2. 머지 충돌난 내 PR → `git rebase origin/main`이 아니라 main을 merge해서 해결 후 푸시 (강제 푸시 금지).
3. **내가(같은 role) 연 PR이** 2개 이상이면 → journal `no_work` 남기고 종료. builder와 builder-b는 서로의 PR·claim을 건드리지 않는다.
4. `ready` 이슈 중 `in-progress`/`blocked`가 아니고 선행 이슈가 모두 닫힌 것. 우선순위: **현재 열린 마일스톤(마감이 가장 이른 것)에 속한 이슈** > `P0`>`P1`>`P2`>`P3`, 같은 등급이면 번호가 작은 것.
   - claim 직후 이슈를 다시 읽어 다른 builder의 CLAIM이 먼저 달렸으면 양보하고 다음 이슈로.
5. `ready` 후보가 없으면 **자가 언블록**: `blocked` 이슈 중 본문 `## 선행`의 이슈가 **모두 closed**이고, 마지막 blocked 사유 코멘트가 선행 대기 외의 이유(NH-*, 외부 자원, needs-split 등)를 들지 않은 것을 찾아 `blocked`를 떼고 `ready`를 붙인 뒤 `UNBLOCK <role> <UTC시각>: 선행 #a,#b closed` 코멘트를 남긴다. 그다음 그 이슈를 정상 절차로 잡는다. 한 실행에 언블록은 최대 2건.
   - 언블록은 상태 라벨만 바꾼다. 권한 라벨(`referee-change`·`harness-change`)은 여전히 Planner·Auditor만 붙인다.
6. 그래도 없으면 journal `no_work` 남기고 종료 (Planner가 채운다).

## 2. 구현
- 이슈를 claim(`harness/PROTOCOL.md` §7). 브랜치 `claude/<번호>-<슬러그>`.
- 시작 전에 관련 코드·문서·ADR을 읽고 계획을 이슈 코멘트로 3~6줄 남긴다.
- 수용 기준 하나하나를 **테스트나 측정으로** 충족시킨다. 테스트는 변경 없이는 실패해야 의미가 있다.
- 보호/하네스 경로는 이슈에 해당 라벨이 있을 때만 수정.
- 동작이 바뀌면 `docs/ARCHITECTURE.md` 등 문서도 같이 고친다.
- 막히면: 이슈에 인수인계 코멘트(시도한 것, 원인 추정, 다음 단계)를 남기고 `blocked` 또는 `needs-split` 라벨, `in-progress` 해제.

## 3. 제출
1. `python -m referee.gates full` 통과.
2. PR 생성: 템플릿을 채우고 수용 기준별로 "어떻게 확인했는지" 적는다. 이슈의 `area:*`·`kind:*`·권한 라벨을 PR에도 붙인다.
3. 스스로 머지하지 않는다. Reviewer가 판정한다.

## 4. 종료
journal에 한 줄(§6). `friction`에 지침·도구·환경 때문에 낭비된 부분을 적는다.
