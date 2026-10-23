# STALKER — 에이전트 운영 지도

토너먼트 포커 AI를 연구해 사람이 학습하는 시스템. **사람은 개입하지 않는다.** 개발·리뷰·머지·하네스 개선은 모두 에이전트(Claude 루틴)가 한다.

## 먼저 읽을 것 (이 순서)
1. `docs/CHARTER.md` — 목적, 불변 요구사항, 북극성 지표. **보호 문서.**
2. `harness/PROTOCOL.md` — 이슈·브랜치·PR·판정·라벨 규칙. 모든 역할 공통.
3. 너의 역할 지침: `harness/routines/<role>.md`
4. 운영 상태: `ops` 브랜치의 `STATE.md` (`git fetch origin ops && git show origin/ops:STATE.md`)
5. 필요할 때만: `docs/HARNESS_DESIGN.md`(하네스 설계), `docs/ARCHITECTURE.md`(코드 구조), `docs/decisions/`(ADR), `docs/research/`

## 절대 규칙
- `harness/PAUSE` 파일이 main에 있으면 아무 작업도 하지 말고 run journal에 `paused`만 남기고 종료.
- **보호 경로**(`referee/PROTECTED_PATHS`)는 `referee-change` 라벨이 붙은 이슈의 작업에서만 수정한다.
- **하네스 경로**(`harness/`, `CLAUDE.md`, `.claude/`, `.github/`)는 `harness-change` 라벨이 붙은 이슈의 작업에서만 수정한다.
- 성능·품질 수치의 근거는 **CI 결과뿐**이다. 직접 돌린 수치는 참고용으로만 쓰고, 그렇다고 표시한다.
- 금지: 강제 푸시, 히스토리 재작성, main 직접 푸시, 리포/브랜치 삭제(머지된 작업 브랜치 제외), secret·브랜치 보호·리포 설정 변경, 외부 공개.
- 한 실행에 한 가지 일. 끝내지 못하면 이슈에 인수인계 코멘트(무엇을 했고, 다음에 무엇을 할지)를 남긴다.
- 실행이 끝날 때 반드시 run journal에 한 줄을 남긴다 (`harness/PROTOCOL.md` §6).

## 개발 환경
```bash
python -m pip install -e ".[dev]"     # Python 3.11+
python -m referee.gates quick         # G0: 테스트·정적검사 (커밋 전 필수)
python -m referee.gates full          # G0+G1(+G2 가능 시): PR 전 필수
```
- 패키지: `stalker/` (제품 L0), `referee/` (심판, 보호), `tests/`.
- 실패 메시지는 짧고, 고치는 방법을 포함하게 작성한다. 성공은 조용히.
- 새 의존성은 `pyproject.toml`에 추가하고 PR 본문에 이유를 쓴다. 순수 Python + numpy 우선.

## 코드 규칙
- 칩은 정수. 난수는 항상 명시적 시드의 `numpy.random.Generator`로 주입(전역 난수 금지) → 재현성.
- 모든 공개 동작에는 테스트. 버그 수정은 실패하던 테스트를 먼저 추가.
- 기록 스키마 변경은 `schema_version`을 올리고 마이그레이션/호환 테스트를 동반.
- 주석은 "왜"만. 문서와 코드가 어긋나면 같은 PR에서 문서도 고친다.
