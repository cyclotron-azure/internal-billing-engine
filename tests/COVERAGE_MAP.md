# Coverage map: `desktop-usage-capture`

Maps every acceptance criterion in `_goals/desktop-usage-capture/00-test-scaffold.md`
through `07-integration.md` to the test node id that verifies it. A criterion with no
test is listed as a **GAP**, not omitted. Committed as of task 07 (the closer); a
reviewer can check this against the suite without rerunning anything, and spot-check
any node id with `python -m pytest <node id> -v`.

Legend: `file::test_name` is a pytest node id relative to `tests/`.

---

## Task 00 — `00-test-scaffold.md`

| Criterion | Test node id(s) |
|---|---|
| 1. `pytest tests/ -q` collects and passes with a scaffold | Property of the whole rung-3 run (`python -m pytest -q`), not one node id — see "Closer run" in this task's completion report. |
| 2. Legacy-schema fixture lacks `usage_source`/`entrypoint` | `test_conftest.py::test_legacy_schema_lacks_new_token_usage_columns`, `test_conftest.py::test_legacy_schema_lacks_new_cost_usage_columns` |
| 3. Transcript fixture covers all 3 entrypoints + malformed line | `test_conftest.py::test_entrypoint_mix_contains_all_three_entrypoints`, `test_conftest.py::test_entrypoint_mix_trailing_line_is_malformed` |
| 3b. Cumulative multi-block + duplicate-pair shapes, published totals = terminal block | `test_conftest.py::test_multiblock_group_terminal_is_highest_api_block_index`, `test_conftest.py::test_multiblock_group_input_and_cache_constant_output_grows`, `test_conftest.py::test_duplicate_pair_both_rows_carry_non_null_stop_reason`, `test_conftest.py::test_recomputed_main_only_totals_match_published` |
| 3c. Sidechain at exact nested path, second project dir, combined > main-only | `test_conftest.py::test_sidechain_file_at_exact_relative_path`, `test_conftest.py::test_sidechain_rows_are_flagged_and_carry_parent_identity`, `test_conftest.py::test_second_project_directory_exists_and_is_distinct`, `test_conftest.py::test_published_totals_combined_strictly_greater_than_main_only` |
| 3d. Flat glob finds fewer files than recursive walk | `test_conftest.py::test_flat_glob_finds_fewer_files_than_recursive_walk`, `test_conftest.py::test_flat_glob_of_projects_root_misses_sidechain_and_is_fewer_than_full_recursive_walk` |
| 4. `bill_otlp_baseline.txt` non-empty, contains basis line | Indirectly by `test_bill.py::test_otlp_only_matches_golden_baseline` (a byte-match against an empty/basis-less file would itself fail) and `test_bill.py::test_golden_baseline_file_is_lf_only`; the capture command itself is documented in `tests/golden/README.md`. |
| 5. Baseline capture is byte-identical across two captures (determinism) | **GAP** — no automated pytest node re-runs the capture script and diffs; verified manually once at task-00 time per `tests/golden/README.md`'s own account. A regression here would only surface as a `test_otlp_only_matches_golden_baseline` failure if `bill.py` itself became non-deterministic, not as a direct determinism check. |

## Task 01 — `01-store-schema.md`

| Criterion | Test node id(s) |
|---|---|
| 1. Migration adds all 4 columns, preserves existing rows | `test_otel_store.py::test_migration_adds_columns_and_preserves_existing_rows` |
| 2. Migration idempotent on second open | `test_otel_store.py::test_migration_is_idempotent_on_second_open` |
| 3. Fresh vs. migrated schema converge (set-equality, ignoring `cid`) | `test_otel_store.py::test_fresh_and_migrated_schemas_converge` |
| 4. Duplicate transcript insert dedupes | `test_otel_store.py::test_duplicate_transcript_insert_dedupes` |
| 5. Differing `request_id` alone produces two rows | `test_otel_store.py::test_differing_request_id_alone_produces_two_rows` |
| 5b. Replay with larger tokens does not overwrite or add | `test_otel_store.py::test_replay_with_larger_tokens_does_not_overwrite_or_add` |
| 6. Transcript cost key never collides with token keys or OTLP `dp_key` | `test_otel_store.py::test_transcript_cost_key_never_collides_with_token_keys_or_otlp_dp_key` |
| 7. `cost_usage` carries queryable `usage_source` | `test_otel_store.py::test_cost_usage_usage_source_is_queryable` |

## Task 02 — `02-transcript-payload.md`

| Criterion | Test node id(s) |
|---|---|
| 1. Well-formed record maps to expected rows | `test_transcript.py::test_ac1_well_formed_record_maps_to_expected_rows` |
| 2. `cli`/`claude-vscode` entrypoint rejected | `test_transcript.py::test_ac2_non_desktop_entrypoint_rejected` |
| 3. Zero/absent `output_tokens` omits the row | `test_transcript.py::test_ac3_zero_output_tokens_omits_output_row`, `test_transcript.py::test_ac3_absent_output_tokens_omits_output_row` |
| 4. Envelope raises `ValueError`; record-level malformations are per-record rejections; valid records in the same batch survive | `test_transcript.py::test_ac4_non_list_envelope_raises_value_error`, `test_ac4_oversized_batch_raises_value_error`, `test_ac4_missing_required_field_is_per_record_rejection`, `test_ac4_negative_token_count_is_per_record_rejection`, `test_ac4_not_a_dict_record_is_rejected`, `test_ac4_unknown_field_is_per_record_rejection`, `test_ac4_cwd_field_is_rejected`, `test_ac4_mixed_batch_good_records_survive_alongside_bad_one` |
| 4b. Two records sharing `(session_id, request_id)`: one accepted, one rejected | `test_transcript.py::test_ac4b_duplicate_request_id_accepts_one_rejects_other` |
| 5. Cost equals `RatingService`'s raw pre-markup value | `test_transcript.py::test_ac5_cost_matches_rating_service_raw_cost` |
| 6. Identity round-trips (`user_email`/`user_id`/`org_id`) | `test_transcript.py::test_ac6_identity_fields_round_trip_onto_every_row` |
| 6b. `query_source` round-trips; invalid value rejected | `test_transcript.py::test_ac6b_query_source_round_trips`, `test_transcript.py::test_ac6b_invalid_query_source_rejected` |
| 7. `repo_raw=''` maps to `unknown`, accepted | `test_transcript.py::test_ac7_empty_repo_raw_maps_to_unknown_and_is_accepted` |
| 8. ssh/https spellings share a repo key | `test_transcript.py::test_ac8_ssh_and_https_spellings_share_repo_key` |
| 9. Emitted `ts` matches the store's column format | `test_transcript.py::test_ac9_emitted_ts_matches_store_column_format`, `test_transcript.py::test_ac9_ts_without_milliseconds_round_trips_exactly` |

## Task 03 — `03-receiver-endpoint.md`

| Criterion | Test node id(s) |
|---|---|
| 1. Authenticated valid batch → 200, rows exist | `test_receiver.py::test_valid_batch_inserts_rows_and_returns_200` |
| 2. Unauthenticated → 401, writes nothing | `test_receiver.py::test_unauthenticated_post_returns_401_and_writes_nothing` |
| 3. Unusable envelope → 400, writes nothing | `test_receiver.py::test_non_list_envelope_returns_400_and_writes_nothing`, `test_receiver.py::test_oversized_batch_returns_400_and_writes_nothing` |
| 3b. Mixed valid/invalid batch → 200, valid inserted, invalid reported rejected | `test_receiver.py::test_mixed_batch_inserts_valid_and_rejects_invalid` |
| 4. Re-POST identical batch → 200, zero new inserts | `test_receiver.py::test_replay_of_identical_batch_inserts_nothing_new` |
| 5. `entrypoint='cli'` rejected, not inserted | `test_receiver.py::test_non_desktop_entrypoint_is_rejected` |
| 6. Identity round-trips end to end | `test_receiver.py::test_identity_round_trips_to_stored_rows` |
| 6b. `main` + `subagent` for same session_id: both stored, distinct `dp_key`s | `test_receiver.py::test_main_and_subagent_rows_preserve_distinct_query_source_and_keys` |
| 7. Malformed-POST log line carries no request bytes | `test_receiver.py::test_malformed_post_log_line_contains_no_request_bytes` |
| 8. Startup banner names `/v1/transcript-usage` | `test_receiver.py::test_startup_banner_mentions_transcript_usage_endpoint` |
| (supplemental, from receiver's own docstring) per-record data-shape errors contained, not escaped | `test_receiver.py::test_wrong_typed_model_field_is_rejected_not_escaped`, `test_receiver.py::test_wrong_typed_session_id_field_is_rejected_not_escaped`, `test_receiver.py::test_store_valueerror_is_caught_per_record_not_whole_batch` |
| (supplemental) genuine operational error rolls back, doesn't orphan uncommitted rows | `test_receiver.py::test_operational_error_rolls_back_instead_of_orphaning_uncommitted_rows` |

## Task 04 — `04-attribution.md`

| Criterion | Test node id(s) |
|---|---|
| 1. Desktop row, no billable repo, WITH timeline row → `desktop-scratch` | `test_attribute.py::test_desktop_scratch_fires_despite_unknown_timeline_row` |
| 2. Desktop row resolving to a real repo → `timeline` | `test_attribute.py::test_desktop_session_resolving_to_real_repo_still_reports_timeline` |
| 3. Existing OTLP classifications unchanged (`timeline`/`wrapper`/`no_remote`/`absent`) | `test_attribute.py::test_every_existing_otlp_classification_unchanged`, `test_attribute.py::test_usage_source_predicate_matters_otlp_unknown_stays_no_remote` |
| 4. `resolved_repo()` unchanged for every seeded OTLP row | `test_attribute.py::test_resolved_repo_unchanged_for_every_seeded_otlp_row` |
| 5. `resolved_view('cost_usage')` compiles, same rows | `test_attribute.py::test_resolved_view_cost_usage_compiles_and_matches` |
| 6. `bill.py` and `export.py` both still run (exit 0) against OTLP-only store | `test_attribute.py::test_bill_py_runs_against_otlp_only_store`, `test_attribute.py::test_export_py_runs_against_otlp_only_store` |
| 7. `resolved_view('token_usage')` yields `resolved_repo`/`attribution_source`, new columns present | `test_attribute.py::test_resolved_view_token_usage_includes_new_columns` |
| (supplemental) branch order / resolved-not-stored-repo edge cases | `test_attribute.py::test_branch_order_matters_scratch_beats_timeline`, `test_attribute.py::test_resolved_repo_not_stored_repo_scratch_launch_cd_into_real_repo`, `test_attribute.py::test_resolved_repo_not_stored_repo_real_launch_cd_into_scratch` |
| **Task 07 routed requirement**: discriminate `_FIRST` from `_AS_OF` (datapoint `ts` precedes every timeline entry) | `test_integration_desktop.py::test_first_arm_resolves_datapoint_preceding_all_timeline_entries`, `test_integration_desktop.py::test_first_arm_mutation_check_neutering_first_falls_through_to_wrapper` (the second test IS the "mutating `_FIRST` to NULL turns this red" proof, via `monkeypatch` rather than a hand-edit of the out-of-fence production file) |

## Task 05 — `05-billing-basis.md`

| Criterion | Test node id(s) |
|---|---|
| 1/1b. Golden byte-match for OTLP-only store, newline-normalized | `test_bill.py::test_otlp_only_matches_golden_baseline`, `test_bill.py::test_golden_baseline_file_is_lf_only` |
| 2. Transcript-only store bills non-zero, labels rate-card | `test_bill.py::test_transcript_only_store_bills_nonzero_and_labels_ratecard` |
| 3. Mixed store bills the sum, states both portions | `test_bill.py::test_mixed_store_bills_sum_and_states_both_portions` |
| 4. Markup applied exactly once | `test_bill.py::test_markup_applied_exactly_once_for_desktop_row` |
| 5. `--basis rates` never re-rates already-rated rows | `test_bill.py::test_basis_rates_recomputes_from_tokens_not_cost_usage` |
| 6. `desktop-scratch` own line in attribution breakdown | `test_bill.py::test_desktop_scratch_line_in_attribution_source`, `test_bill.py::test_desktop_scratch_absent_for_otlp_only` |
| 7. otlp+transcript overlap warning fires/doesn't, doesn't change total | `test_bill.py::test_overlap_session_triggers_warning`, `test_bill.py::test_no_overlap_session_no_warning`, `test_bill.py::test_overlap_detector_does_not_change_billed_total` |
| 8. Invoice `.txt` distinguishes actual from estimated | `test_invoice.py::test_txt_distinguishes_actual_from_estimated`, `test_invoice.py::test_txt_actual_only_store_has_no_estimate_subtotal` |
| 8b. `summary.csv`/`line_items.csv` never label an estimate as actual | `test_invoice.py::test_summary_csv_splits_actual_and_estimated`, `test_invoice.py::test_line_items_csv_splits_actual_and_estimated`, `test_invoice.py::test_summary_csv_no_estimate_for_actual_only_store` |
| 9. Invoice regeneration semantics untouched | `test_invoice.py::test_regeneration_replaces_line_items_in_place` |

## Task 06 — `06-client-hook.md`

| Criterion | Test node id(s) |
|---|---|
| 1. Only desktop entrypoint ships | `test_transcript_hook.py::test_ac1_only_desktop_entrypoint_ships` |
| 1b. Exact amount: terminal block, not sum, not first | `test_transcript_hook.py::test_ac1b_exact_amount_terminal_block_not_sum_not_first` |
| 1c. Exact-duplicate pair collapses to one record | `test_transcript_hook.py::test_ac1c_duplicate_pair_both_nonnull_stop_reason_collapses_to_one` |
| 1d/1d-bis. Subagent capture against real nested layout; anti-fixture check | `test_transcript_hook.py::test_ac1d_and_1d_bis_subagent_capture_and_anti_fixture` |
| 1e. `query_source` correct per file; shared repo | `test_transcript_hook.py::test_ac1e_query_source_and_shared_repo`, `test_transcript_hook.py::test_ac1e_classifies_by_isSidechain_flag_not_by_subagents_path` |
| 1f. Missing `apiBlockIndex` selects by file order without raising | `test_transcript_hook.py::test_ac1f_missing_apiblockindex_selects_by_file_order_without_raising`, `test_transcript_hook.py::test_ac1f_apiblockindex_wins_over_file_order_when_they_disagree` |
| 2. No message content in payload | `test_transcript_hook.py::test_ac2_no_message_content_in_payload` |
| 3. Payload validates against the real server-side validator | `test_transcript_hook.py::test_ac3_payload_validates_against_server_validator` |
| 4. Exits 0 on unreachable receiver / missing transcript / missing `~/.claude.json` / empty stdin | `test_transcript_hook.py::test_ac4_exits_zero_missing_transcript_missing_claude_json_empty_stdin`, `test_ac4_exits_zero_receiver_unreachable_with_real_transcript`, `test_ac4_exits_zero_with_garbage_billing_timeout` |
| 5. Malformed final line skipped, preceding records ship | `test_transcript_hook.py::test_ac5_malformed_trailing_line_skipped_preceding_records_ship` |
| 6. Running twice ships each record once | `test_transcript_hook.py::test_ac6_running_twice_ships_each_record_once` |
| 7. Persistent 400 doesn't advance state; drops after bound | `test_transcript_hook.py::test_ac7_persistent_400_dropped_after_bound_state_advances`, `test_ac7_growing_batch_poison_record_eventually_drops_others_still_ship` |
| 7b. Overlapping sessions, older `SessionEnd` fires last, both ship | `test_transcript_hook.py::test_ac7b_overlapping_sessions_older_ends_last_both_ship` |
| 7c. 200-with-rejections advances state, no retry | `test_transcript_hook.py::test_ac7c_200_with_rejections_advances_state_no_retry` |
| 7d. Never-fired `SessionEnd`, across project directories | `test_transcript_hook.py::test_ac7d_never_fired_session_end_across_project_dirs` |
| 7e. Forward-only install watermark | `test_transcript_hook.py::test_ac7e_forward_only_install_watermark` |
| 7f. In-flight group not shipped partially | `test_transcript_hook.py::test_ac7f_inflight_group_not_shipped_partially_then_ships_at_terminal` |
| 7g. Abandoned in-flight group still ships | `test_transcript_hook.py::test_ac7g_abandoned_inflight_group_still_ships` |
| 7h. Transport failure never drops, eventually ships | `test_transcript_hook.py::test_ac7h_transport_failure_never_drops_eventually_ships` |
| 8. Never opens `~/.claude/.credentials.json` | `test_transcript_hook.py::test_ac8_never_reads_credentials_json_static`, `test_ac8_never_reads_credentials_json_dynamic` |
| 9. `deploy/managed-settings.json` valid, preserves existing, adds new | `test_configure.py::test_managed_settings_is_valid_json_dict`, `test_managed_settings_preserves_every_existing_registration`, `test_managed_settings_registers_transcript_hook_session_end_only`, `test_managed_settings_preserves_placeholder_token_convention` |
| (supplemental, task 06b rollout) client-package build, `pilot-package` untouched, `.gitattributes` pins | `test_configure.py::test_transcript_hook_copies_are_equal_after_newline_normalization`, `test_build_contents_includes_transcript_hook`, `test_build_contents_files_all_exist_on_disk`, `test_pilot_package_not_touched`, `test_gitattributes_pins_deploy_py_to_lf`, `test_gitattributes_marks_golden_baseline_as_binary`, `test_gitattributes_preserves_preexisting_entries`, `test_git_check_attr_reports_lf_for_deploy_python_hooks`, `test_version_bumped_past_1_1_0` |

## Task 07 — `07-integration.md` (this task)

| Criterion | Test node id(s) |
|---|---|
| 1. `python -m pytest -q` passes from repo root | See "Closer run" in this task's completion report (257 passed, twice). |
| 2. Two consecutive full-suite runs both pass, no manual cleanup | See "Closer run" in this task's completion report. |
| 3. End-to-end exact billed amount; none of the three historical errors | `test_integration_desktop.py::test_end_to_end_desktop_path_exact_billed_amount` |
| 4. Scratch-workspace path reaches billing as `desktop-scratch` | `test_integration_desktop.py::test_scratch_workspace_reaches_billing_as_desktop_scratch` |
| 5. Mixed OTLP+transcript store bills each exactly once, overlap silent | `test_integration_desktop.py::test_mixed_otlp_and_transcript_store_bills_each_once_no_overlap` |
| 6. `export.py` builds both CSVs after all changes | `test_export.py::test_both_lake_csvs_build_for_mixed_store`, `test_export.py::test_export_runs_against_otlp_only_store` |
| 7. `tests/COVERAGE_MAP.md` exists, maps every criterion or lists it a GAP | This file. |
| **Routed requirement 1** — discriminate `_FIRST` from `_AS_OF` | `test_integration_desktop.py::test_first_arm_resolves_datapoint_preceding_all_timeline_entries`, `test_first_arm_mutation_check_neutering_first_falls_through_to_wrapper` |
| **Routed requirement 2** — systemic-failure alarm (100% `store_error:` rejection rate) | `test_integration_desktop.py::test_systemic_alarm_fires_on_closed_database`, `test_systemic_alarm_fires_on_map_record_key_rename_regression`, `test_systemic_alarm_silent_for_ordinary_mixed_batch`, `test_systemic_alarm_silent_for_pure_validation_rejections`, `test_systemic_alarm_silent_when_batch_is_entirely_clean`; plus `test_actually_closed_database_escapes_past_the_per_record_guard` (a related FINDING — see completion report) |
| **Routed requirement 3** — `transcript_key` does not strip | `test_integration_desktop.py::test_transcript_key_contract_does_not_strip_request_id` |
| **Routed requirement 4** — cross-task `_mark_resolved` key seam (seeded, asserted, NOT fixed) | `test_integration_desktop.py::test_cross_task_key_seam_second_group_permanently_lost` — see this task's completion report for the measured token/dollar loss and the FINDING routing note |
| export.py: transcript rows, correct UTC date columns | `test_export.py::test_transcript_rows_appear_with_correct_utc_date_columns`, `test_export.py::test_transcript_row_token_and_cost_totals_are_correct_in_lineitems` |
| export.py: no `cost_source` column (pinned Out of Scope) | `test_export.py::test_export_emits_no_cost_source_column_pinned_out_of_scope` |
| Hygiene (no network/live service, `tmp_path`/`:memory:` only, outcome assertions, no extra dependency) | Enforced throughout `test_export.py` and `test_integration_desktop.py`; nothing binds a port, every store is a `tmp_path` file, no import beyond `pytest` + stdlib + `billing`/`deploy` modules under test. |

---

## GAPs (explicit)

1. **Task 00 AC1** (bare collection with zero tests) has no single dedicated node id — it is a property of the whole suite at scaffold time, not something task 07 can re-verify in isolation (the scaffold now has hundreds of tests). Not a functional gap; recorded for completeness.
2. **Task 00 AC5** (golden baseline capture is byte-identical across two captures) has no automated pytest node. It was verified once, manually, at task-00 time (per `tests/golden/README.md`'s own account of the capture procedure) and is not re-provable after the fact without re-running the original capture script against pre-task-01 code, which no longer exists in the working tree. A regression here would only be visible indirectly, via `test_bill.py::test_otlp_only_matches_golden_baseline` failing if `bill.py`'s OTLP-only output ever became non-deterministic.
