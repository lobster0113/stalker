# 공개 포커 AI·솔버 조사 (2026-10-24, 부트스트랩 세션)

## 질문
신진서 9단이 KataGo를 쓰듯, 토너먼트 NLHE에서 "그냥 가져다 쓸" 충분히 강한 공개 AI가 있는가? (헌장 7)

## 결론
**없다.** 토너먼트용 KataGo에 해당하는 것은 존재하지 않는다.
- 공개 가중치의 초인 수준 NLHE 에이전트 없음. Pluribus 코드 미공개, ReBeL 코드는 Liar's Dice만, DeepStack 코드는 Leduc만.
- 프로그램으로 접근 가능한 강한 봇(Slumbot API, GTO Wizard Researcher API)은 **헤즈업 200bb 캐시 전용이고 행동 하나만 반환**한다(혼합전략 미제공).
- 최강의 토너먼트 도구(GTO Wizard: 9인 프리플랍 ICM, 3인 ICM 포스트플랍 / HRC Pro: ICM+FGS, 멀티웨이)는 **상용 GUI이고 공개 API가 없다.** 자동화 시 약관 위반 가능성이 있고, 사람의 구매·설치(Windows)가 필요하다 → 사람 무개입 원칙과 충돌.
- 실질적 "엔진"은 **스팟별 솔버 조합**이다.

## 활용 가능 구성요소 (자동화·클라우드 가능한 것 위주)
| 구성요소 | 용도 | 라이선스/접근 | 비고 |
|---|---|---|---|
| PokerKit (uoftcprg) | 게임 규칙·상태·사이드팟·앤티(BB앤티 포함), PHH 포맷 | MIT, 순수 Python, 테스트 커버리지 99% | 자체 엔진 대신 사용 후보 |
| TexasSolver 콘솔 (bupticybee) | 헤즈업 포스트플랍 GTO 혼합전략(JSON) | AGPL-3.0(개인 사용 OK), Linux 지원 | Pio와 정확도 동급 주장; 플랍 수 분 소요; ICM 미지원 |
| b-inary postflop-solver | 포스트플랍 솔버(Rust 라이브러리) | AGPL, 개발 중단(2023-10) | 대안 |
| OpenSpiel universal_poker | CFR 계열 연구용 프레임워크 | Apache-2.0 | 추상화 게임 풀이 |
| PHH 데이터셋 | Pluribus 1만 핸드, ACPC 2.79억 핸드 등 | MIT | 참조 데이터 |
| Slumbot API / GTO Wizard Researcher API | 헤즈업 강도 벤치마크 | 무료 / 키 신청 | 전략 소스 불가, 측정용 |
| 상용(HRC Pro, PioSolver+UPI, ICMIZER, GTO Wizard) | ICM/FGS 프리플랍, 멀티웨이 | 유료, GUI 위주 | 사람 구매 필요 → 선택 사항으로만 |

## 공백 (직접 메워야 하는 것)
1. **토너먼트 프리플랍 ICM/FGS 솔버** — 공개·자동화 가능한 것 없음(취미 수준 ICM/푸시폴드 코드만). 순수 ICM은 잼/폴드 스팟을 잘못 가격매길 수 있어 FGS 고려 필요(arXiv 2608.09586).
2. **ICM 반영 포스트플랍** — TexasSolver는 칩EV. 리스크 프리미엄 변환 등 근사 필요.
3. **멀티웨이 포스트플랍** — 신뢰할 공개 솔버 없음.
4. **정보 누적 적응** — 공개 도구는 노드락/스탯 기반 수동 조정뿐. 연구(AlphaExploitem 등) 코드 미공개.
5. **대규모 처리량** — 풀 솔브는 스팟당 분 단위 → 수백만 결정(`referee/DATA_SUFFICIENCY.md`)은 "풀어둔 전략 라이브러리 + 조회/보간"으로만 가능.

## 위험
- 솔버 출력은 트리(벳 사이즈·추상화)와 에퀴티 모델(칩EV/ICM/FGS)에 좌우 → 모든 결과에 가정을 기록해야 함.
- 상용 도구 자동화의 약관 문제, AGPL의 재배포 제한(개인용이라 문제없음).
- 실시간 플레이 보조 금지: 이 시스템은 오프테이블 학습 전용.

## 출처
- Pluribus 비공개: https://www.technologyreview.com/2019/07/11/134224/
- GTO Wizard vs Slumbot, Researcher API: https://blog.gtowizard.com/crushing-a-top-hunl-poker-bot/ , https://github.com/gtowizard-ai/researcher-api-client , https://arxiv.org/abs/2603.23660
- GTO Wizard ICM 기능(2026): https://www.pokernews.com/news/2026/09/gto-wizard-now-comes-with-preflop-icm-solving-52401.htm
- HRC: https://www.holdemresources.net/docs/postflop/ , https://www.holdemresources.net/news
- TexasSolver: https://github.com/bupticybee/TexasSolver
- postflop-solver: https://github.com/b-inary/postflop-solver
- PokerKit: https://github.com/uoftcprg/pokerkit , PHH: https://github.com/uoftcprg/phh-dataset
- OpenSpiel universal_poker: https://github.com/google-deepmind/open_spiel
- ICM 오가격 연구: https://arxiv.org/abs/2608.09586 , 적응 연구: https://arxiv.org/abs/2605.09150
- 일부 2026년 수치는 요약을 통해 확인됨 — 의존 전 원문 재확인 필요(Researcher 루틴 과제).
