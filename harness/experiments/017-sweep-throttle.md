# 017: reviewer 스윕 간격을 이전 스윕끼리만 비교
- 상태: 진행 중
- 제안: builder, 2026-10-27 / 이슈 #205 / PR (이 PR)
## 문제 (관측 근거)
- `should_run.py reviewer --sweep`은 journal의 마지막 실행(웹훅 실행 포함)과 비교해 1시간 스로틀을 걸었다. 웹훅 실행이 잦으면 스윕이 매번 `SKIP (last run 0:00:45 ago < 1h)`로 끝났다(10-27 17:23Z).
- 그래서 새 이벤트가 없는 PR, 즉 CI success 뒤 판정만 기다리는 PR이 판정되지 않았다. #190·#200이 gates success 뒤 약 2시간 기다렸고, 라벨을 뗐다 붙여 웹훅을 일으키는 임시 조치를 썼다.
## 가설
스윕끼리만 간격을 재면 웹훅 빈도와 상관없이 스윕이 1시간마다 돈다. CI success 뒤 판정까지 걸리는 시간이 1시간(+CI 대기) 안으로 줄어든다.
## 변경
- `harness/should_run.py`: `--sweep` RUN이 잠금과 **같은 커밋**으로 `ops:locks/<role>.sweep.json`(role·run_id·started)을 쓴다. `decide()`는 스윕일 때 `last_sweep(role)`(그 파일)과 비교한다. 스윕이 아닌 실행은 기존처럼 journal의 `last_run`과 비교한다. 파일이 없거나 깨졌으면 "no previous sweep"로 RUN한다(스윕이 한 번 더 도는 것이 멈추는 것보다 낫다). role 이름은 하드코딩하지 않아 reviewer·reviewer-b 모두 쓴다.
- 잠금 동작(`lock_hours`, SKIP running)은 그대로다. `--release`는 `locks/<role>.json`만 지우고 스윕 시각은 남긴다.
## 측정 지표와 측정창
머지 후 7일. (1) PR의 필수 체크가 모두 success가 된 시각부터 첫 `VERDICT`까지 걸린 시간의 중앙값. 기준값은 10-27 #190·#200의 약 2시간이다. (2) reviewer·reviewer-b 스윕 실행(`--sweep` RUN) 수 / 경과 시간.
## 성공 기준
(1) 중앙값 1시간 이하, (2) role마다 하루 20회 이상 스윕 RUN(잠금 SKIP 제외).
## 롤백 방법
이 PR을 revert. 남은 `ops:locks/*.sweep.json`은 읽는 코드가 없어지므로 무해하다(지워도 된다).
## 결과
(측정창 종료 후 auditor가 기록)
