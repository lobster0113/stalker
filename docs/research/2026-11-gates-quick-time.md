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

## A+C 뒤 (#816)

> 이 절의 수치도 **로컬 참고값(CI 아님)**. CI는 full을 돌리므로 quick 단축 효과는 CI 잡 시간에 직접 드러나지 않는다(reviewer-b 11-12 15:06Z friction).

### 측정 환경과 총 시간
- main `69b482a8`(c1323cd1 이후, #808 slow 마커·#811 quick xdist 포함), Python 3.11, Intel Xeon 2.10GHz **4코어**, pytest 9.2.0, pytest-xdist 3.8.0, numba 없음(순수 Python).
- `python -m referee.gates quick`: **197초**(compile 0초, tests 197초). 같은 선택을 `-n auto --dist worksteal -v --durations=0`으로 두 번 더 돌려 195.0초·195.9초. 1731 수집 / 98 deselected(slow), 1729 passed, 7 skipped.
- 워커 수: `-n auto` → **4**(`created: 4/4 workers`).
- 수집: `pytest --collect-only -q -m "not slow"` **1.15초**(프로세스 전체 1.5초). `import stalker, referee, numpy`는 0.09초.
- 이슈 본문의 "≈520초"(builder 11-12 16:09Z)는 이번 세 번의 측정에서 재현되지 않았다. 같은 머신에서 다른 작업과 겹친 측정이었을 가능성이 있다(원인은 확인하지 못함). 아래 분석은 195초 측정에서 나온 것이다.

### 워커 부하 — 불균형은 없다
| 워커 | 테스트 수 | 바쁜 시간 합(초) |
|---|---|---|
| gw0 | 445 | 188.9 |
| gw1 | 238 | 190.3 |
| gw2 | 553 | 192.0 |
| gw3 | 432 | 192.8 |

(0.005초 미만 항목은 pytest가 숨겨 합계가 1668개 기준이다.) 테스트 시간 합(setup 27.4 + call 736.5 + teardown 0.1)은 **764초**이고, 4로 나누면 191초다. 실제 벽시계 196초와 4~7초밖에 차이 나지 않는다. worksteal이 이미 거의 완벽하게 나누고 있다. 25초가 넘는 단일 테스트가 없으므로 "한 테스트가 하한을 정한다"는 #800의 걱정(C안)도 이제는 해당하지 않는다.
**결론: 지금 quick의 하한은 `테스트 시간 합 ÷ 코어 수`다.** 워커 배정, 수집, 임포트는 합쳐도 5초 안쪽이다. 시간을 줄이려면 테스트 시간 합 자체를 줄여야 한다.

### 상위 30개 (xdist 하, setup+call+teardown)
| # | nodeid | 초 | 워커 |
|---|---|---|---|
| 1 | tests/test_vcfr_fixed_point.py::test_fixed_ranges_never_churn | 24.1 | gw3 |
| 2 | tests/test_e3_preflop_probe.py::test_probe_flags_the_served_mid_policy_limping_aces | 22.6 | gw1 |
| 3 | tests/test_e3_mix_counts.py::test_checkpoint_resume_counts_as_one_run | 18.7 | gw1 |
| 4 | tests/test_e3_mix_counts.py::test_result_and_summary_carry_the_counts | 17.7 | gw1 |
| 5 | tests/test_persona_ladder.py::test_fidelity_levels_1_7_13_19 | 14.8 | gw2 |
| 6 | tests/test_metrics.py::test_gate_f_metrics_are_deterministic_and_ordered | 14.7 | gw2 |
| 7 | tests/test_train_jobs.py::test_league_job_records_generations_and_the_champion | 14.3 | gw3 |
| 8 | tests/test_web_vectors.py::test_committed_vectors_cover_the_spec_and_are_current | 12.8 | gw3 |
| 9 | tests/test_e3_b1_cost.py::test_batched_next_card_equities_match_the_per_card_reference | 12.0 | gw0 |
| 10 | tests/test_e3_determinism.py::test_e3_fingerprint_is_identical_under_emulated_runners | 12.0 | gw0 |
| 11 | tests/test_persona_ladder.py::test_level_19_beats_level_1_headsup | 11.2 | gw2 |
| 12 | tests/test_e3_mix_counts.py::test_per_size_counts_add_up_to_the_run | 10.8 | gw1 |
| 13 | tests/test_web_vectors.py::test_generator_tiny_build_has_the_schema | 10.2 | gw3 |
| 14 | tests/test_e2_exploiter.py::test_exploiter_beats_an_untrained_uniform_policy | 9.9 | gw0 |
| 15 | tests/test_e3_mix_counts.py::test_version_6_checkpoint_counts_from_where_it_resumes | 9.9 | gw1 |
| 16 | tests/test_e3_field.py::test_chance_terms_are_unbiased_and_keep_the_action_stream | 9.5 | gw1 |
| 17 | tests/test_web_hit_rate.py::test_play_backoff_levels_are_exact_and_the_trajectory_differs_from_uniform_play | 8.7 | gw3 |
| 18 | tests/test_gate_l.py::test_pipeline_checks_pass_and_gate_runner_reports | 8.5 | gw2 |
| 19 | tests/test_train_jobs.py::test_league_xbase_job_trains_the_exploiter_on_the_baseline_abstraction | 8.4 | gw3 |
| 20 | tests/test_e3_replay_worker.py::test_checkpoint_replays_bit_identical_in_another_process[default] | 8.0 | gw1 |
| 21 | tests/test_web_hit_rate.py::test_l4_counts_a_level_and_off_is_byte_identical | 7.3 | gw3 |
| 22 | tests/test_e2_personas.py::test_uniform_random_loses_to_tag | 7.2 | gw0 |
| 23 | tests/test_e2_league.py::test_league_records_generations_and_promotes_only_on_a_lower_exploit_gain | 7.1 | gw0 |
| 24 | tests/test_metrics.py::test_gate_l_snapshot_keys_and_ranges | 7.1 | gw2 |
| 25 | tests/test_web_hit_rate.py::test_fidelity_off_is_byte_identical_and_needs_play_backoff | 7.0 | gw3 |
| 26 | tests/test_web_vectors.py::test_node_port_matches_vectors | 6.9 | gw3 |
| 27 | tests/test_e3_preflop_probe.py::test_probe_is_reproducible_and_worker_independent | 6.1 | gw1 |
| 28 | tests/test_hand.py::test_invariants_random_hands | 6.1 | gw2 |
| 29 | tests/test_info_contract.py::test_l7_checks_pipelines_and_registered_policies | 5.7 | gw2 |
| 30 | tests/test_e3_menu.py::test_gate_r_pokerkit_replay_on_new_rules[tp6-3] | 5.7 | gw1 |

상위 30개 합은 325초(합 764초의 43%)다. 나머지 약 1640개가 439초를 쓴다. 꼬리가 길다.

### 같은 산출물을 다시 만드는 묶음
"절감"은 테스트 시간 합(워커-초)이 줄어드는 양이다. 벽시계 절감은 대략 그 ÷4다.

| 묶음 | 지금(초) | 다시 만드는 것 | 약화 없는 축소 방법 | 예상 절감(워커-초) |
|---|---|---|---|---|
| `test_e3_mix_counts.py` 5개(`checkpoint_resume`·`per_size`·`version_6`·`pod_checkpoint`·`counting_draws`) | 46 | 각 테스트가 같은 `_c1()`(seed 3, mix 2·3·6)을 새로 만들어 3~18회 반복(합 약 45회) | 모듈 범위 픽스처에 `iterate(3)`·`(4)`·`(5)`·`(9)` 시점 `state()`를 한 번씩만 만들어 두고, 각 테스트는 `E3MCCFR.from_state(copy)`로 이어 받는다. 해시·카운트 단언은 그대로 둔다 | ≈ 25 |
| `test_e3_mix_counts.py::test_result_and_summary_carry_the_counts` | 18 | 시드 2개 × `e3_evaluate`(작은 LBR/field 손 수에서도 평가 준비 비용) | 시드 1개로 줄이면 `by_players_counts_by_seed` 길이 2 검사가 약해진다 → **축소하지 않음**, slow 후보 | 0 (slow면 18) |
| `test_web_hit_rate.py`의 "off는 바이트 동일" 3개 + `play_backoff_levels` | 28 | 매 `H.main` 호출(테스트당 3~4회)이 2.5MB `mid-3.json`을 다시 읽고 준비한다. 측정: 2손 2.3초, 20손 4.1초 → 호출당 고정비 약 1.7초 | 테스트 쪽에서 로드된 정책을 모듈 픽스처로 공유(`H`에 이미 로드된 정책을 받는 진입점이 필요하면 제품 코드 변경), 손 수는 그대로 | ≈ 15 |
| `test_metrics.py::test_gate_l_snapshot_keys_and_ranges` + `test_gate_l.py::test_pipeline_checks_pass_and_gate_runner_reports` | 16 | 둘 다 Gate L 파이프라인 검사 전체를 돌린다 | 세션 범위 픽스처(`conftest.py`) 하나로 `metrics.gate_l()` 결과를 공유. 단 워커가 다르면 공유가 안 되므로 같은 파일로 모으거나 `--dist loadfile`류 그룹 지정이 필요 | ≈ 7 |
| `test_web_vectors.py` `tiny_build` + `committed_vectors_are_current` | 23 | 둘 다 `W.build`를 따로 부른다(1손·1반복 vs 커밋된 파라미터) | 같은 파라미터가 아니라 공유하면 스키마 테스트의 "작은 빌드" 의도가 사라진다 → 축소하지 않음 | 0 |
| `test_metrics.py::test_gate_f_metrics_are_deterministic_and_ordered` | 15 | `gate_f_e1()`을 결정성 확인용으로 두 번 | 두 번 부르는 것이 테스트의 본질 → 축소하지 않음, slow 후보 | 0 (slow면 15) |
| `test_persona_ladder.py` 2개 | 26 | 레벨별 충실도 + 6000손 헤즈업 | 손 수 축소는 통계 검정력을 낮춘다 → slow 후보 | 0 (slow면 26) |
| `test_e3_preflop_probe.py::test_probe_flags_the_served_mid_policy_limping_aces` | 23 | 서빙 정책 로드 + 300손 프로브(#391 발견을 고정하는 회귀) | 손 수 축소는 플래그 한계를 바꾼다 → slow 후보 | 0 (slow면 23) |

입력 축소/공유(D안)로 약화 없이 줄일 수 있는 양은 **약 45~50워커-초(벽시계 약 12초)** 다. slow 후보 4개(18+15+26+23=82워커-초, 벽시계 약 20초)를 더해도 quick은 약 195 → **약 165초**가 된다.

### 90초 목표는 현재 테스트 구성으로는 비현실적이다
- 4코어, 불균형 0을 가정하면 90초 = 테스트 시간 합 약 **350초 이하**(오버헤드 5초 제외)다. 지금은 764초이므로 **약 415워커-초**를 빼야 한다.
- 상위 30개(325초)를 전부 slow로 옮겨도 나머지 439초 ÷ 4 ≈ **110초**다. 90초에 닿으려면 상위 약 60개를 옮기거나(full로 미루는 범위가 커져 quick의 회귀 탐지력이 크게 떨어진다), 코어 수가 8 이상인 환경이 있어야 한다.
- 따라서 quick 목표는 이 환경(4코어) 기준으로 **약 150~165초**가 현실적인 근거 있는 수치다. builder.md 목표 수치 변경은 이 이슈의 범위 밖이며, 바꿀지는 하네스 이슈로 판단한다.

### 다음 구현 이슈 추천
1. **[gates quick 단축 D-1] `test_e3_mix_counts.py` `_c1()` 상태 공유 + `test_web_hit_rate.py` 정책 로드 공유** — 대상: `tests/test_e3_mix_counts.py::{test_checkpoint_resume_counts_as_one_run,test_per_size_counts_add_up_to_the_run,test_version_6_checkpoint_counts_from_where_it_resumes,test_pod_checkpoint_carries_the_counts,test_counting_draws_no_random_numbers}`, `tests/test_web_hit_rate.py::{test_miss_report_off_is_byte_identical_and_needs_play_backoff,test_l4_counts_a_level_and_off_is_byte_identical,test_fidelity_off_is_byte_identical_and_needs_play_backoff,test_play_backoff_levels_are_exact_and_the_trajectory_differs_from_uniform_play}`. 예상 절감 약 40워커-초(벽시계 약 10초). 단언(해시·바이트 동일성)은 그대로 둔다. 권한 라벨 필요 없음(`tests/`는 보호 경로가 아니다. `stalker/tools/web_hit_rate.py`에 진입점을 추가하면 제품 코드도 함께 바뀐다).
2. **[gates quick 단축 A-2] 통계·결정성 테스트 4개를 `slow`로** — `tests/test_persona_ladder.py::{test_fidelity_levels_1_7_13_19,test_level_19_beats_level_1_headsup}`, `tests/test_e3_preflop_probe.py::test_probe_flags_the_served_mid_policy_limping_aces`, `tests/test_metrics.py::test_gate_f_metrics_are_deterministic_and_ordered`. 예상 절감 약 78워커-초(벽시계 약 20초). full(G1)에서는 계속 실행된다. 권한 라벨 필요 없음.

둘을 합쳐도 quick은 약 165초다. 그 아래로 내리려면 목표 수치를 다시 정하거나 러너 코어 수를 늘리는 결정(하네스/예산)이 필요하다.
