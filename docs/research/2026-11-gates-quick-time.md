# gates quick 소요 시간 분해 (#800)

> 모든 수치는 **로컬 참고값(CI 아님)**. CLAUDE.md 규칙: 성능 근거는 CI 결과뿐이다. 후속 이슈의 절감 확인은 CI 잡 시간으로 한다.

## 측정 환경
- 명령: `python -m pytest -q -m "not slow" --durations=0 -p no:cacheprovider` (quick의 `-x --no-header`를 뺀 같은 선택)
- Python 3.11.18, CPU 4코어, `pip install -e ".[dev]"` (`.[fast]`/numba **없음**, 평가기는 순수 Python 경로), pytest-xdist 설치돼 있으나 **quick은 직렬 실행**(`-n` 없음, `referee/gates.py:59`).
- 결과: `1723 passed, 7 skipped, 84 deselected in 1716.7s (28분 36초)`. call+setup+teardown 합 1712.9초(0.005초 미만 항목은 pytest가 숨김). 목표 90초의 약 19배.
- 1회 측정이라 분산은 모른다(같은 날 journal의 1468~1560초와 같은 규모).

## 표 3 — quick 단계별 시간
| 단계(`_run` 이름) | 명령 | 초 |
|---|---|---|
| compile | `compileall -q stalker referee harness` | 0.05 |
| tests | `pytest -q -x -m "not slow"` | ≈1717 |

quick은 이 두 단계뿐이다. 시간의 사실상 전부가 tests다. setup/teardown은 33.5초(2%)로 픽스처 비용은 작다.

## 표 1 — 가장 느린 테스트 30개 (setup+call+teardown)
| # | nodeid | 초 |
|---|---|---|
| 1 | tests/test_export_web_players.py::test_cli_policies_out_index_lists_only_uploaded_files_of_this_run | 230.3 |
| 2 | tests/test_pod_train.py::test_oversized_model_falls_back_to_float32_then_summary_only | 100.3 |
| 3 | tests/test_pod_train.py::test_run_writes_a_checked_result_and_unpacks_to_the_ci_layout | 95.4 |
| 4 | tests/test_export_web_policy.py::test_average_strategy_and_pod_result_input | 88.5 |
| 5 | tests/test_e3_seat_probs.py::test_b1_path_matches_per_value_mask_reference | 65.0 |
| 6 | tests/test_export_web_players.py::test_per_player_min_visits_is_applied_and_recorded_per_file | 51.3 |
| 7 | tests/test_web_personas.py::test_persona_calibration | 45.9 |
| 8 | tests/test_export_web_players.py::test_hit_rate_is_measured_with_the_files_own_menu_and_cap | 41.8 |
| 9 | tests/test_persona.py::test_fidelity_20k_hands_within_5pp | 34.8 |
| 10 | tests/test_metrics.py::test_snapshot_has_no_retired_keys | 31.6 |
| 11 | tests/test_metrics.py::test_snapshot_includes_gate_l | 31.5 |
| 12 | tests/test_metrics.py::test_training_metrics_are_exact_and_deterministic | 30.2 |
| 13 | tests/test_vcfr_fixed_point.py::test_fixed_ranges_never_churn | 29.6 |
| 14 | tests/test_e3_preflop_probe.py::test_probe_flags_the_served_mid_policy_limping_aces | 24.0 |
| 15 | tests/test_e3_mix_counts.py::test_checkpoint_resume_counts_as_one_run | 20.7 |
| 16 | tests/test_train_jobs.py::test_league_job_records_generations_and_the_champion | 20.1 |
| 17 | tests/test_e3_mix_counts.py::test_result_and_summary_carry_the_counts | 19.1 |
| 18 | tests/test_metrics.py::test_gate_f_metrics_are_deterministic_and_ordered | 18.2 |
| 19 | tests/test_persona_ladder.py::test_level_19_beats_level_1_headsup | 14.9 |
| 20 | tests/test_web_vectors.py::test_committed_vectors_cover_the_spec_and_are_current | 14.3 |
| 21 | tests/test_persona_ladder.py::test_fidelity_levels_1_7_13_19 | 14.1 |
| 22 | tests/test_e3_determinism.py::test_e3_fingerprint_is_identical_under_emulated_runners | 12.7 |
| 23 | tests/test_e2_exploiter.py::test_exploiter_beats_an_untrained_uniform_policy | 12.4 |
| 24 | tests/test_e3_b1_cost.py::test_batched_next_card_equities_match_the_per_card_reference | 12.3 |
| 25 | tests/test_e3_mix_counts.py::test_per_size_counts_add_up_to_the_run | 11.8 |
| 26 | tests/test_e3_mix_counts.py::test_version_6_checkpoint_counts_from_where_it_resumes | 11.6 |
| 27 | tests/test_web_vectors.py::test_generator_tiny_build_has_the_schema | 11.1 |
| 28 | tests/test_e3_field.py::test_chance_terms_are_unbiased_and_keep_the_action_stream | 10.4 |
| 29 | tests/test_web_hit_rate.py::test_play_backoff_levels_are_exact_and_the_trajectory_differs_from_uniform_play | 10.3 |
| 30 | tests/test_gate_l.py::test_pipeline_checks_pass_and_gate_runner_reports | 9.9 |

상위 30개 합계는 약 1,124초(전체의 약 66%). 이 30개를 뺀 나머지가 약 590초.

## 표 2 — 파일별 합계 상위 15개
| 파일 | 테스트 수 | 초 | 전체 대비 % |
|---|---|---|---|
| tests/test_export_web_players.py | 8 | 335.0 | 19.6 |
| tests/test_pod_train.py | 14 | 203.5 | 11.9 |
| tests/test_metrics.py | 20 | 121.5 | 7.1 |
| tests/test_export_web_policy.py | 14 | 95.1 | 5.6 |
| tests/test_e3_mix_counts.py | 9 | 74.2 | 4.3 |
| tests/test_e3_seat_probs.py | 1 | 65.0 | 3.8 |
| tests/test_train_jobs.py | 20 | 55.5 | 3.2 |
| tests/test_web_hit_rate.py | 19 | 50.0 | 2.9 |
| tests/test_web_personas.py | 1 | 45.9 | 2.7 |
| tests/test_info_contract.py | 10 | 37.1 | 2.2 |
| tests/test_e3_preflop_probe.py | 5 | 37.1 | 2.2 |
| tests/test_persona.py | 3 | 35.4 | 2.1 |
| tests/test_web_vectors.py | 8 | 33.5 | 2.0 |
| tests/test_vcfr_fixed_point.py | 4 | 33.4 | 1.9 |
| tests/test_persona_ladder.py | 2 | 29.0 | 1.7 |

(테스트 수는 0.005초 이상으로 기록된 항목만 센다.) **상위 15개 파일 합계는 전체 테스트 시간의 73.0%.** 상위 4개 파일(export_web_players·pod_train·metrics·export_web_policy)만으로 44%.

## 단축안 (절감은 로컬 참고값)
| 안 | 내용 | 예상 절감 | 바꿀 파일 | 권한 라벨 |
|---|---|---|---|---|
| A | 표 1 상위 ~12개(각 30초 이상, 합계 약 847초)에 `@pytest.mark.slow` 부착. full(G1)은 slow를 포함하므로 검증 범위는 유지, quick에서만 빠진다 | ≈ -850초 (1717→≈870) | `tests/test_export_web_players.py`, `test_pod_train.py`, `test_export_web_policy.py`, `test_e3_seat_probs.py`, `test_web_personas.py`, `test_persona.py`, `test_metrics.py` | 없음 (`tests/`는 `referee/PROTECTED_PATHS`에 없음, 확인함) |
| B | 파일 A와 더해 상위 15개 파일의 무거운 테스트 전부(약 2~30초대)까지 slow 처리 | ≈ -1,250초 (→≈450) | 위 + `test_e3_mix_counts.py`, `test_train_jobs.py`, `test_web_hit_rate.py`, `test_info_contract.py` 등 | 없음 |
| C | quick의 pytest에 `-n auto --dist worksteal`(full과 동일) 추가. 4코어 기준 이론상 1/3~1/4, 단일 거대 테스트(230초)가 하한 | ≈ -1,100~1,200초 (→≈500~600, 거대 테스트에 묶임) | `referee/gates.py` | `referee-change` (보호 경로) |
| D | 무거운 테스트의 입력 축소(예: 훈련 반복 수·손 수 감소, 큰 픽스처를 세션 범위로 공유). 거대 테스트 1~5번이 같은 export/훈련 산출물을 각자 다시 만드는지 확인 필요 | 후보 1~5번만 해도 최대 ≈ -400~500초 | 각 테스트와 `tests/conftest.py` | 없음. 단 테스트가 보증하는 동작을 약화하면 안 됨 |
| E | 순수 Python 평가기 대신 numba(`.[fast]`) 설치로 훈련 계열 테스트 가속 | 미측정(이번에 numba 없이만 쟀다) | 환경 설치 단계(`.github/`/루틴 환경) | `harness-change` |

주의: A·B는 quick이 잡던 회귀를 PR 시점이 아니라 full(G1)에서 잡게 만든다. 단 full은 PR 전 필수라 범위 손실은 없고 시점만 늦어진다. C는 quick을 90초 근처로 내릴 수는 없다(거대 테스트가 하한).

## 추천
**A를 먼저, 그다음 D의 1번 테스트(230초)를 별도 손질.** 이유: 권한 라벨이 필요 없어 Builder가 바로 할 수 있고, 한 번에 약 850초를 줄이며 되돌리기 쉽다. 90초 목표는 A+D+C를 모두 해야 닿는다(후속으로 단계 진행).

## 후속 이슈 초안
**제목:** [gates quick 단축 1/n] 가장 느린 테스트 12개를 `slow` 마커로 옮기기

```
## 목표
`gates quick`(`-m "not slow"`)에서 개당 30초 이상 걸리는 테스트를 slow로 옮겨 quick 시간을 줄인다. full(G1)은 slow를 포함하므로 검증은 유지된다.

## 수용 기준 (모두 검증 가능해야 함)
- [ ] docs/research/2026-11-gates-quick-time.md 표 1의 1~12번(각 약 30초 이상) 테스트에 `@pytest.mark.slow`가 붙는다. 테스트 본문·단언은 바꾸지 않는다.
- [ ] `python -m pytest --collect-only -q -m "not slow"`의 선택 개수가 12개 줄고, `-m slow` 선택에 같은 12개가 있다(PR 본문에 개수 기록).
- [ ] CI gates(tests) 잡(또는 PR 체크)의 quick 소요 시간이 이전 main 실행보다 줄었는지 CI 잡 시간으로 확인해 PR 본문에 적는다.
- [ ] full(G1)에서 이 12개가 여전히 실행되어 통과한다(CI로 확인).
- [ ] `python -m referee.gates quick` 통과.

## 범위 밖
- `referee/gates.py`·ci.yml 수정, 테스트 삭제·skip, 입력 축소(D안).

## 선행
- 없음 (#800 머지 후)

## 참고
- docs/research/2026-11-gates-quick-time.md 표 1, 단축안 A
- CLAUDE.md "성능 수치 근거는 CI"
```
