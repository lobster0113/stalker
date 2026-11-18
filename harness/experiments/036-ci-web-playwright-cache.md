# 036: CI web 잡 playwright 브라우저 캐시·설치 재시도·install-deps 최선 노력
- 상태: 진행 중
- 제안: builder-b, 2026-11-11 / 이슈 #780 / PR #783
## 문제 (관측 근거)
- 11-11 ~15:00Z부터 `web` 잡의 `npx playwright install --with-deps chromium`이 apt(security.ubuntu.com) DNS 해석 실패로 반복 실패했다(main 9ed6a58f run 43036927811 재실행 포함, PR #776·#778 web 4회). Gate U(`npm test`)가 한 줄도 돌지 않아 리뷰어가 MERGE를 못 내고 main이 빨강이었다(STATE 경보 planner 11-11 15:20Z·17:35Z, journal reviewer-b 15:48Z·16:30Z).
- web 잡 `timeout-minutes: 15`는 정상 실행(~12분)에 가까워 재시도 여유가 없었다.
## 가설
브라우저 빌드를 캐시하고 설치를 재시도하며 시스템 의존성 설치를 실패 허용으로 바꾸면(ubuntu-latest에 라이브러리 기본 포함) 일시적인 apt 장애가 web 잡을 깨지 않는다.
## 변경
- `.github/workflows/ci.yml` web 잡: `~/.cache/ms-playwright`를 `actions/cache@v4`로 캐시(키 `web/e2e/package-lock.json` 해시), 적중 시 install 생략, `playwright install chromium` 3회 재시도(20·40초 백오프), `--with-deps` 제거 후 `install-deps`는 3회·`timeout 120`·실패 시 경고로 통과, `timeout-minutes` 15→25.
- `tests/test_harness.py`: timeout 상한 단언 15→25.
## 측정 지표와 측정창
머지 후 14일. 근거는 CI web 잡 로그.
- install/apt 원인으로 실패한 web 잡 수.
- 캐시 적중률(캐시 단계 `cache-hit`), install-deps 경고 발생 수.
- web 잡 총 시간.
## 성공 기준 (수치)
- 측정창 안 install/apt 원인 web 실패 0건.
- web 잡 시간 중앙값 ≤ 15분, 최댓값 < 25분.
- 이 PR의 web 잡 success(확인됨: run 43085560819).
## 롤백 방법
이 PR을 revert한다. web 잡은 `--with-deps` 한 줄 설치와 15분 timeout으로 돌아간다.
## 결과 (측정창 종료 후 기록)
