# 학습 페이지 프로토타입

빌드 도구 없는 정적 웹앱. 화면 2개: 유형 목록(셀별 행동 빈도 + 표본 충분성 배지), 퀴즈(스팟 → 내 선택 → AI 행동 분포 비교).

## 로컬 실행
```bash
python -m stalker.pipeline.generate --preset sng6 --n 30 --seed 1 --out runs/sng6-s1   # 유형화 리포트 + 기록
python -m stalker.service.build runs/sng6-s1 --out service/web/data                     # report.json, quiz.json 복사·생성
cd service/web && python -m http.server 8000                                           # http://localhost:8000
```
`data/`에 들어 있는 것은 참조 봇 3게임짜리 **샘플**이다(대부분 셀이 "데이터 부족"으로 보이는 게 정상). 배포(Artifact/GitHub Pages)는 별도 작업이다.

## 메모
- 퀴즈의 EV 손실은 기록에 `action_values`가 있을 때만 계산한다. 참조 봇 기록에는 없어서 지금은 표시하지 않는다.
- 진행 기록은 localStorage(`stalker.quiz.v1`). 막혀 있어도 동작한다.
- 외부 CDN 의존 없음.
