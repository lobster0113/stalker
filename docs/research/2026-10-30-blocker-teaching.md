# 블로커 교수법 조사 — `hand.block` 정의 근거 (#395)

날짜: 2026-10-30. 조사 방법: WebSearch 요약만 사용, 원문 전문 미확인(참고용). 사이트 대부분이 교육 사이트라 빈도 수치는 예시로만 본다.

## 질문
코치들은 블로커를 어떻게 가르치는가? `hand.block`(#395)을 초보가 따라 할 수 있는 판단 단계로 정의하려면 무엇을 넣어야 하나?

## 핵심 발견
1. 블로커 = 내가 쥔 카드가 상대 레인지에서 지우는 콤보. 예: A♥를 쥐면 상대는 A♥K♥ 등을 못 가진다. ([DeucesCracked](https://www.deucescracked.com/learn/poker-glossary/blockers), [PokerSkill](https://www.pokerskill.com/poker-glossary/blockers/))
2. **블러프 선택의 핵심은 "상대의 콜 핸드를 지우고 폴드 핸드는 지우지 않는 것".** 폴드 핸드를 지우는 블로커는 오히려 해롭다. 대표 실수: 부서진 플러시 드로우(같은 무늬 두 장)가 블로커라고 믿는 경우. ([DeucesCracked 가이드](https://www.deucescracked.com/blog/poker-blockers-card-removal-bluffing-guide), [GTO Wizard](https://blog.gtowizard.com/blockers-unblockers-the-secret-to-picking-great-bluffs/))
3. 넛 플러시 무늬 3장 보드에서 그 무늬 A를 쥐면 넛 플러시를 지운다. 놓친 스트레이트 드로우가 놓친 플러시 드로우보다 좋은 블러프 후보인 경우가 많다(콜 핸드를 더 지움). ([TournamentPokerEdge](https://www.tournamentpokeredge.com/utilizing-blockers-effectively-in-poker))
4. 블로커는 양방향이다: 블러프 캐처는 상대 밸류를 지우면 콜 근거가 강해지고, 밸류벳은 상대의 약한 콜 핸드를 지우지 않는 편이 낫다. ([DeucesCracked 블러프캐칭](https://www.deucescracked.com/blog/poker-bluff-catching-river-call-down-strategy))
5. 블로커는 블러프를 **만들지** 않고 다듬는다: 팟오즈·레인지 구성이 먼저, 블로커는 보조. 

## STALKER 함의
- #395의 `hand.block` 정의("지우는 상대 밸류·넛 근처 콤보 비율")는 발견 2·4의 **절반**이다. 두 값으로 나누는 편이 가르치기 쉽다: `block_value`(상대 밸류 지움 → 블러프·콜에 유리)와 `block_fold`(상대 폴드/약한 콜 핸드 지움 → 블러프에 불리, 밸류벳에도 불리). 최소한 TP 설명 문구에 "콜 핸드를 지우는가, 폴드 핸드를 지우는가"를 질문 형태로 넣을 것.
- 채점 UI에서 "블로커가 있다"만 보여주면 부서진 FD 오해를 강화한다. 피드백은 **무엇을 지우는지**를 명시해야 한다.
- 2번 결과는 `hand.outs`와 무관하게 리버 블러프 선택 단계에만 의미가 있으므로 적용 스트리트는 리버(와 턴 세미블러프)로 제한하는 것이 자연스럽다.

## 위험
- 출처가 요약 수준이라 정량 기준(몇 % 이상이 "블로커")은 근거 없음 → 정의는 보드 평균 대비 상대값으로 두고 임계는 측정 후 정할 것.
- `block_fold`를 별도 항목으로 두면 key 차원이 늘어 둔감성·단순성 제약(ADR 0009)과 충돌 가능.

## 추천
1. #395 builder는 `hand.block` 문구에 "콜 핸드 vs 폴드 핸드" 구분을 포함한다(별도 항목 신설은 key 크기 측정 후 결정).
2. B1 측정 노트(#398 후)에서 `block_value`만 쓴 key와 둘 다 쓴 key를 비교한다 — 후보, 이슈화는 #398 머지 후 planner.

(후속 이슈는 만들지 않음: #395가 이미 ready이며 추천 1은 코멘트로 전달.)
