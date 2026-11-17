# 040: RunPod DNS/연결 거부 지연 재시도 (POST create) + GET/DELETE 짧은 재시도
- 상태: 진행 중
- 제안: builder-b, 2026-11-16 / 이슈 #946 / PR #947
## 문제 (관측 근거)
11-16 16:45Z부터 GitHub 러너에서 `rest.runpod.io` 이름 해석이 실패해 `mode=run` 포드 생성이 모두 실패했다(run 43911033715·43925339150·43930925362). 비용은 $0이지만 디스패치와 클라우드 임계 경로(#937)가 막혔다.
## 가설
생성 POST를 DNS(`socket.gaierror`)·연결 거부(`ConnectionRefusedError`)일 때만 1·5·15분 대기 뒤 재시도하면 일시 장애에서 회복한다. 이 두 오류는 RunPod가 요청을 보기 전에 일어나므로 포드가 중복 생성되지 않는다. 타임아웃·리셋은 요청 전송 뒤에도 날 수 있어 재시도하지 않는다. GET/DELETE는 멱등이라 5·15초 재시도한다.
## 변경
`harness/cloud/launcher.py`: `NETWORK_RETRY_MINUTES`, `NETWORK_RETRY_SECONDS`, `_is_prerequest_error`. 실패한 시도는 원장 줄을 남기지 않는다.
## 측정 지표와 측정창
머지 뒤 14일 동안의 `mode=run` 디스패치. 원장·journal·run 로그에서 센다.
## 성공 기준
- URLError(DNS)로 끝난 run 0건, 또는 재시도 창(약 21분) 안에서 회복한 run 존재
- 중복·추적 안 된 포드 0건(reap orphan 0)
## 롤백 방법
`NETWORK_RETRY_MINUTES`를 `()`로 두거나 PR #947을 revert한다.
## 결과 (측정창 종료 후 기록)
- 11-17 중간 기록(#952): 11-16 실패의 원인은 일시 장애가 아니라 RunPod REST v1(`rest.runpod.io/v1`) 은퇴(2026-11-15, 공식 v1→v2 이전 안내)였다. 재시도로는 회복할 수 없어 launcher를 v2 `api.runpod.io/v2`로 옮겼다. 측정창의 DNS 실패 run은 이 원인으로 분류하고, 재시도 효과는 이전 뒤 run으로만 판단한다.
