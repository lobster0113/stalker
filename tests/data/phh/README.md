# PHH 공개 핸드 기록 (SIM-f, #148)

- 출처: https://github.com/uoftcprg/phh-dataset, 디렉터리 `data/pluribus/` (Brown & Sandholm 2019 보충자료의 Pluribus 10,000핸드, 6인 노리밋 홀덤 100BB, 앤티 없음).
- 고정 커밋: `e47fbd5816372360bade4de5d712346fe1bb70f6`
- 라이선스: MIT (Copyright (c) 2024-2025 Universal, Open, Free, and Transparent Computer Poker Research Group). 재배포 허용. 이 README와 아래 설명이 고지를 겸한다.
- 파일: `pluribus.jsonl.gz` — 위 10,000핸드 중 정렬 순서로 5개마다 1개, 2,000핸드(약 96KB). 한 줄이 한 핸드이고 PHH 필드 그대로에 `id`(`<디렉터리>/<파일>`)만 더했다.
- 재생성: `python -m referee.gate_r.phh build <phh-dataset>/data/pluribus tests/data/phh/pluribus.jsonl.gz --step 5`
- 검사: `python -m referee.gate_r.phh check` 또는 `pytest tests/test_phh_replay.py` (네트워크 불필요, 약 4초).
- 배제 사유 코드(`referee.gate_r.phh.exclusion`): `variant`·`ante`·`straddle_or_blinds`·`min_bet`·`empty_seat`·`players`·`hidden_cards`·`fractional_chips`(기록이 홀수 칩을 반으로 나눈 핸드; 우리 칩은 정수). 샘플 2,000핸드 중 배제는 `fractional_chips` 1건(41b/204), 나머지 1,999핸드는 `Hand`·`FastHand` 모두 기록된 최종 스택과 칩 단위로 일치.
- 대안 출처(이번엔 쓰지 않음): 같은 저장소의 `handhq`(2009 온라인 로그 2,160만 핸드, 6~10인), WSOP 2023 최종 테이블 83핸드. 1만 핸드 확장은 v1 결과를 보고 후속 이슈.
