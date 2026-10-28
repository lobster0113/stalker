# 014: CPU 학습은 GitHub Actions 러너에서 (train.yml)
- 상태: 진행 중
- 제안: 대화 세션, 2026-10-27 / 이슈 #184 / PR (이 PR)
## 문제
유료 연산(RunPod) 런처는 파드를 만들고 종료할 뿐, 출력을 돌려받지 않는다. 그래서 학습 결과·정책 파일을 회수할 방법이 없다. 게다가 MCCFR 같은 CPU 학습에는 RunPod 비용을 쓸 이유가 없다.
## 가설
공개 리포라 GitHub 표준 러너가 무료다(잡당 6시간, 병렬 matrix). CPU 학습을 여기서 돌리면 비용 0으로 시드 병렬 학습을 하고, 결과를 아티팩트와 ops 요약으로 바로 회수할 수 있다. RunPod은 GPU 학습에만 쓴다.
## 변경
- `.github/workflows/train.yml`: workflow_dispatch(잡 이름·반복·시드 수 1..8) → 시드별 matrix → 아티팩트(30일) → 요약을 `ops:training/<job>/<run id>.json`에 push. 입력은 env로만 받는다. 비밀 정보 없음.
- `stalker/train_jobs.py`: 허용 목록(JOBS) 잡만 실행한다. 지금은 `e2-mccfr`(MCCFR + LBR 400핸드).
## 측정 지표와 측정창
첫 실행부터 14일. (1) 학습 실행 수와 성공률, (2) 시드당 반복/초(로컬 대비), (3) RunPod 비용 대비 절감액(같은 작업을 RunPod CPU로 했을 때의 추정).
## 성공 기준
(1) 성공률 ≥ 90%, (2) 로컬과 같은 자릿수, (3) CPU 학습 RunPod 지출 0.
## 롤백 방법
이 워크플로를 지운다(다른 워크플로와 독립).
## 결과
(측정창 종료 후 auditor가 기록)
