# referee/ — 심판 (보호 경로)

STALKER의 모든 "좋아졌다/나빠졌다" 판정은 여기의 코드가 CI에서 계산한다. 선수(Builder)는 심판을 고칠 수 없다.
수정은 `referee-change` 라벨이 붙은 이슈에서만, Reviewer의 심판 변경 추가 검토(`harness/routines/reviewer.md` §1-5)를 거쳐서만 가능하다.

| 파일 | 역할 |
|---|---|
| `PROTECTED_PATHS` | 라벨별 보호 경로 |
| `guard.py` | PR이 보호 경로를 라벨 없이 바꾸면 CI 실패 |
| `gates.py` | G0/G1/G2 게이트 (`quick`, `full`) |
| `metrics.py` | main 머지마다 `ops:metrics/history.jsonl`에 append되는 지표 스냅샷 |

## 앞으로 추가될 것 (Planner가 `referee-change` 이슈로 관리)
- 엔진 불변식 퍼저(G1), 재현성 체크(G1)
- 벤치마크 봇 필드 + 토너먼트 평가(ROI·ICM $EV, 신뢰구간) (G2)
- 적응 가치 평가: 적응형 vs 사전정보 고정 AI (G2)
- 이론 앵커: 숏스택 push/fold 내시 대비 EV 손실 (G2)
- 챔피언 리그·승급 (main 머지 후)
- 홀드아웃 평가: `HOLDOUT_SEED` GitHub Secret 사용, 일 1회 (에이전트는 시드를 볼 수 없다)
- 유형화 지표: 커버리지·안정성·증류 충실도
