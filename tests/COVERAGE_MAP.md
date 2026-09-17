# Coverage maps

This file indexes one section per goal, mapping every acceptance criterion in that
goal's task files to the pytest node id(s) that verify it. A criterion with no test is
listed as a **GAP**, not omitted. A reviewer can check any section against the suite
without rerunning anything, and spot-check any node id with `python -m pytest <node id>
-v`.

Legend: `file::test_name` is a pytest node id relative to `tests/`.

---

# Coverage map: `desktop-usage-capture`

Maps every acceptance criterion in `_goals/desktop-usage-capture/00-test-scaffold.md`
through `07-integration.md` to the test node id that verifies it. Committed as of task
07 (the closer).

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

---

# Coverage map: `reconcile-coverage-diagnostics`

Maps every acceptance criterion in `_goals/reconcile-coverage-diagnostics/01-store-dedupe-counter.md`
through `03-reconcile-output.md` to the test node id(s) that verify it. Tasks 01-03 landed
and passed evaluation before this task (04) existed, so every row below is regression
coverage written after the fact, against the shipped interface -- not TDD alongside the
implementation. Criterion 01.15 (`pytest tests/test_otel_store.py -q` exits 0) is a
command-output criterion, not a unit test, and is intentionally not represented as a row.

## Task 01 — `01-store-dedupe-counter.md`

| Criterion | Test node id(s) |
|---|---|
| 1. `dedupe_drops` schema: 6 columns, 3-col PK | `test_dedupe_counter.py::test_ac1_dedupe_drops_schema` |
| 2. Duplicate OTLP insert True/False, day from datapoint ts | `test_dedupe_counter.py::test_ac2_duplicate_insert_true_then_false_day_from_datapoint_ts` |
| 3. Third duplicate raises drops to 2, advances last_seen, keeps first_seen | `test_dedupe_counter.py::test_ac3_third_duplicate_advances_last_seen_not_first_seen` |
| 4. Successful insert adds no dedupe_drops row | `test_dedupe_counter.py::test_ac4_successful_insert_adds_no_dedupe_drops_row` |
| 5. Duplicate transcript / cost drops counted correctly | `test_dedupe_counter.py::test_ac5_transcript_and_cost_duplicates_counted_correctly` |
| 6. Legacy migration adds `dedupe_drops`, preserves rows, idempotent | `test_dedupe_counter.py::test_ac6_legacy_migration_adds_dedupe_drops_preserves_rows` |
| 7. Never-inserted store has `dedupe_epoch() is None` | `test_dedupe_counter.py::test_ac7_never_inserted_store_has_no_epoch` |
| 8. Epoch set on first insert, unchanged across reopen | `test_dedupe_counter.py::test_ac8_epoch_set_on_first_insert_unchanged_across_reopen` |
| 9. Epoch set by successful first insert / duplicate-only first insert | `test_dedupe_counter.py::test_ac9_epoch_set_by_successful_first_insert`, `test_dedupe_counter.py::test_ac9_epoch_set_by_duplicate_only_first_insert` |
| 10. Latch closes after exactly one post-commit meta SELECT | `test_dedupe_counter.py::test_ac10_latch_closes_after_exactly_one_meta_select_post_commit` |
| 11. Rolled-back first epoch write recovered on next insert | `test_dedupe_counter.py::test_ac11_rollback_of_first_epoch_write_is_recovered` |
| 12. Half-open window for `dedupe_drops`/`dedupe_drops_by_day` | `test_dedupe_counter.py::test_ac12_half_open_window_for_dedupe_reads` |
| 13. Counter UPDATE failure: no raise, no residue via public readers | `test_dedupe_counter.py::test_ac13_counter_update_failure_does_not_raise_or_break_insert` |
| 14. Epoch write failure: no raise, correct return value | `test_dedupe_counter.py::test_ac14_epoch_write_failure_does_not_raise_or_break_insert` |
| 15. `pytest tests/test_otel_store.py -q` exits 0 | Command-output criterion, not a unit test (see note above). |

## Task 02 — `02-reconcile-aggregation.md`

| Criterion | Test node id(s) |
|---|---|
| 1. Pre-change baseline pin (`otel_totals` captured/tagged) | `test_reconcile.py::test_02_1_baseline_captured_and_tagged_pinned` |
| 2. Unmapped token type reported with correct total | `test_reconcile.py::test_02_2_unmapped_token_type_reported_with_correct_total` |
| 3. NULL `token_type` reported under `"(none)"` | `test_reconcile.py::test_02_3_null_token_type_reported_as_none` |
| 4. `otel_by_surface` dimensions sum to `captured_total` | `test_reconcile.py::test_02_4_by_surface_dimensions_sum_to_captured_total` |
| 5. NULL `entrypoint`/`query_source` coalesce to `"(none)"` | `test_reconcile.py::test_02_5_null_entrypoint_and_null_query_source_coalesce_to_none` |
| 6. Sigma-daily == period, captured + tagged | `test_reconcile.py::test_02_6_daily_sums_equal_period_totals_captured_and_tagged` |
| 7. Sigma-daily == period, truth side (org-wide + user-scoped) | `test_reconcile.py::test_02_7_daily_sums_equal_totals_org_wide`, `test_reconcile.py::test_02_7_daily_sums_equal_totals_user_scoped` |
| 8. Day-key literal normalized, matches `otel_daily`'s key | `test_reconcile.py::test_02_8_day_key_normalized_and_matches_otel_daily` |
| 9. Org-wide path makes exactly one `usage_report` call | `test_reconcile.py::test_02_9_single_pass_call_count_is_exactly_one` |
| 10. `analytics_claude_code_totals` sums the single pass correctly | `test_reconcile.py::test_02_10_totals_wrapper_sums_daily_for_fixed_fake_payload` |
| 11. `AnalyticsError` from `usage_report` -> existing message | `test_reconcile.py::test_02_11_analytics_error_from_usage_report_produces_existing_message` |
| 12. `analytics_claude_code_daily` returns a materialized dict eagerly | `test_reconcile.py::test_02_12_daily_returns_materialized_dict_eagerly` |
| 13. 5 epoch placements -> `measurement` | `test_reconcile.py::test_02_13_measurement_states_for_five_epoch_placements` (parametrized, 5 cases) |
| 14. `otel_daily`'s tagged reflects the resolved (not raw) repo | `test_reconcile.py::test_02_14_daily_tagged_reflects_resolved_repo` |
| 15. No aggregation function prints anything | `test_reconcile.py::test_02_15_aggregation_functions_print_nothing` |
| 16. `counts_outside_measurement`: both routes True, `full` False | `test_reconcile.py::test_02_16_counts_outside_measurement_true_replayed_export_route`, `test_reconcile.py::test_02_16_counts_outside_measurement_true_interrupted_write_route`, `test_reconcile.py::test_02_16_counts_outside_measurement_false_when_fully_counted` |

## Task 03 — `03-reconcile-output.md`

| Criterion | Test node id(s) |
|---|---|
| 1. Default `run()` prints only the 3 base sections | `test_reconcile.py::test_03_1_default_run_prints_only_base_sections` |
| 2. `BY TOKEN TYPE` rows + `TOTAL` pinned exactly (whitespace included) | `test_reconcile.py::test_03_2_by_token_type_rows_and_total_pinned_exactly` |
| 3. Unmapped section prints type + exact count, default invocation | `test_reconcile.py::test_03_3_unmapped_section_prints_type_and_count` |
| 4. No unmapped types -> no section | `test_reconcile.py::test_03_4_no_unmapped_section_when_empty` |
| 5. Four qualifiers distinct wording; no bare count when `by_type` empty | `test_reconcile.py::test_03_5_four_qualifiers_wording_and_no_bare_count_when_empty`, `test_reconcile.py::test_03_5_all_four_states_pairwise_different` |
| 6. `partial` state names epoch, says lower bound (with drops) / says the window's undropped portion was never counted (empty `by_type`) | `test_reconcile.py::test_03_6_partial_state_with_drops_names_epoch_and_says_lower_bound`, `test_reconcile.py::test_03_6_partial_state_with_empty_by_type_names_epoch_no_lower_bound` |
| 7. `full` state: zero drops says "no duplicates"; nonzero prints counts | `test_reconcile.py::test_03_7_full_state_zero_drops_says_no_duplicates`, `test_reconcile.py::test_03_7_full_state_nonzero_drops_prints_exact_count` |
| 7b. Non-empty `by_type` printed under states 1, 2, 3 with qualifier | `test_reconcile.py::test_03_7b_nonempty_by_type_printed_under_states_1_2_3` (parametrized, 3 cases) |
| 7c. `counts_outside_measurement` names both count and epoch | `test_reconcile.py::test_03_7c_counts_outside_measurement_names_count_and_epoch` |
| 8. `--daily` prints a truth-only day with a coverage pct | `test_reconcile.py::test_03_8_daily_prints_truth_only_day_with_coverage_pct` |
| 9. `--daily` rows sum to the period `TOTAL` | `test_reconcile.py::test_03_9_daily_rows_sum_to_period_total` |
| 10. `--daily` works in `--email` mode, renders tagged/billable | `test_reconcile.py::test_03_10_daily_in_email_mode_renders_tagged_and_billable` |
| 11. Per-day dedupe sub-table renders under every measurement state | `test_reconcile.py::test_03_11_per_day_dedupe_subtable_renders_in_state_full`, `test_reconcile.py::test_03_11_per_day_dedupe_subtable_renders_in_state_none_with_epoch` |
| 12. `--by-surface` header + 3 dimensions + `(none)` entrypoint row | `test_reconcile.py::test_03_12_by_surface_header_and_dimensions_and_none_entrypoint` |
| 13. Each `--by-surface` sub-block `TOTAL` reads exactly `100.00%` | `test_reconcile.py::test_03_13_by_surface_total_rows_read_100_percent` |
| 14. `--detail` contains both daily and surface section headers | `test_reconcile.py::test_03_14_detail_contains_daily_and_surface_headers`, `test_reconcile.py::test_main_detail_implies_by_surface_and_daily` |
| 15. No-analytics-rows path and `AnalyticsError` path unchanged, no funnel | `test_reconcile.py::test_03_15_no_analytics_rows_path_prints_hint_and_no_funnel`, `test_reconcile.py::test_03_15_analytics_error_path_prints_existing_message_and_no_funnel` |
| 16. Rule lines equal length; no output line exceeds it | `test_reconcile.py::test_03_16_rule_lines_equal_length_and_no_line_exceeds_them` |

## Regression coverage (untested `--email` / org-wide `run()` paths)

| Behavior | Test node id(s) |
|---|---|
| `analytics_user_totals` returns `None` for zero matching rows | `test_reconcile.py::test_regression_user_totals_none_when_zero_rows` |
| `analytics_user_totals` shape (`CANON` mapping) and email/date scoping | `test_reconcile.py::test_regression_user_totals_shape_and_scoping` |
| Email matching is case/whitespace-insensitive | `test_reconcile.py::test_regression_email_matching_case_and_whitespace_insensitive` |
| `otel_totals(..., emails=[...])` scopes captured/tagged | `test_reconcile.py::test_regression_otel_totals_scopes_by_email` |
| `--email` path, empty analytics: hint printed, no funnel | `test_reconcile.py::test_regression_email_path_empty_analytics_prints_hint_no_funnel` |
| `--email` path, zero OTEL rows: normal zeroed funnel, no `SYNTHETIC` note | `test_reconcile.py::test_regression_email_path_zero_otel_rows_prints_normal_funnel_no_synthetic` |

## GAPs (explicit)

None. Every requirement item and acceptance criterion in `04-tests.md` that calls for a
unit test has one; criterion 01.15 is a command-output criterion by design (see note
above), and criterion 15 of task 01 is the only such item in this goal.

Two deliberate, spec-mandated non-pins are **not** GAPs (they are wording-independent
properties instead of verbatim string pins, per an explicit orchestrator deviation
since Phase 5 changes both): the exact wording of the `partial`-with-empty-`by_type`
sentence, and the `__cost__` row's column offsets. Both are still covered --
`test_03_5_four_qualifiers_wording_and_no_bare_count_when_empty` asserts the qualifier
text and the absence of a bare count without pinning full-sentence punctuation beyond
that, and no test in this file asserts a byte-offset for the `__cost__` label.

---

# Coverage map: `otel-export-loss-reduction`

Maps every acceptance criterion in `_goals/otel-export-loss-reduction/01-export-interval.md`,
`02-store-reads.md`, `03-receiver-health-and-cli-ingest.md`,
`04-sweeper-cli-backfill.md` and `06-otlp-session-id-coercion.md` to the test node
id(s) that verify it. Task 06's criteria live in `tests/test_receiver_health.py`
(alongside task 03) because both tasks modify `billing/otel/receiver.py`'s ingest
paths and task 06's fix (`_common`'s session-id coercion) is exercised through the
same `/v1/metrics` + `/v1/transcript-usage` harness. Task 01's criteria live in
`tests/test_cli_backfill.py` alongside task 04, per this task's write fence.

## Task 01 — `01-export-interval.md`

| Criterion | Test node id(s) |
|---|---|
| 1. All four config sources carry `10000`; `dev-selftest.sh` keeps `5000` | `test_cli_backfill.py::test_01_ac01_all_four_config_sources_carry_10000_dev_selftest_keeps_5000` |
| 2. `managed-settings.json` / `pilot-package/settings.json` carry string `"10000"` | `test_cli_backfill.py::test_01_ac02_managed_settings_and_pilot_settings_carry_string_10000` |
| 3. `configure.py` parses; defaults dict resolves to `"10000"` | `test_cli_backfill.py::test_01_ac03_configure_py_parses_and_defaults_resolve_to_10000` |
| 4. `install.sh` parses; emitted settings block is valid JSON with the new value | `test_cli_backfill.py::test_01_ac04_install_sh_parses_and_emits_valid_json_with_new_value` |
| 5. No `60s`/`60000` describing the current export interval in `deploy/README.md`/`README.md` | `test_cli_backfill.py::test_01_ac05_no_60s_or_60000_describing_current_interval` |
| 6. `git diff --stat` touches exactly the six files in task 01's write set | `test_cli_backfill.py::test_01_ac06_git_diff_stat_touches_exactly_the_six_files` |
| 7. No pre-existing test asserts the old `60000` value | `test_cli_backfill.py::test_01_ac07_no_test_asserts_the_old_60000_value` |

## Task 02 — `02-store-reads.md`

| Criterion | Test node id(s) |
|---|---|
| 1. `last_ingest_at()` on empty store returns `None` | `test_store_reads.py::test_ac01_last_ingest_at_empty_store_returns_none` |
| 2. Max across both tables, insert order irrelevant | `test_store_reads.py::test_ac02_last_ingest_at_is_max_across_both_tables_out_of_order` |
| 3. `usage_source` filter actually filters (one fixture, two assertions) | `test_store_reads.py::test_ac03_usage_source_filter_ignores_newer_transcript_row` |
| 4. Reads `ingested_at`, not `ts` | `test_store_reads.py::test_ac04_reads_ingested_at_not_ts` |
| 5. Empty input: `set()`, zero queries (execute-spy) | `test_store_reads.py::test_ac05_empty_session_ids_returns_empty_set_zero_queries` |
| 6. 1200 ids, 3 exist -> those 3, 3 statements | `test_store_reads.py::test_ac06_chunking_over_1200_ids_three_exist_three_statements` |
| 7. 600 copies of one id -> 1 id, 1 statement | `test_store_reads.py::test_ac07_600_duplicate_ids_dedupe_to_one_statement` |
| 8. Transcript-only excluded; OTLP+transcript included | `test_store_reads.py::test_ac08_transcript_only_session_excluded_mixed_session_included` |
| 9. `entrypoint IS NULL` OTLP row is returned, built via `insert_datapoint` | `test_store_reads.py::test_ac09_entrypoint_null_otlp_row_is_returned` |
| 10. SQL metacharacter session id: no match, no raise | `test_store_reads.py::test_ac10_sql_metacharacter_session_id_no_match_no_raise` |
| 11. Both methods write nothing (execute-spy + full-file sha256) | `test_store_reads.py::test_ac11_read_methods_write_nothing_spy_and_sha256` |
| 12. `git diff` on `otel_store.py` is additions only | `test_store_reads.py::test_ac12_git_diff_otel_store_is_additions_only` |
| 13. C1: cost-only session via `insert_cost_datapoint` alone is returned | `test_store_reads.py::test_ac13_cost_only_session_via_insert_cost_datapoint_alone_is_returned` |
| 14. `last_ingest_at` reflects a newer `cost_usage` row, filtered and unfiltered | `test_store_reads.py::test_ac14_last_ingest_at_reflects_newer_cost_row` |
| 15. Parameter-cap regression: 500-id chunk under `setlimit(999)` | `test_store_reads.py::test_ac15_full_500_id_chunk_succeeds_under_999_variable_cap` |

## Task 03 — `03-receiver-health-and-cli-ingest.md`

| Criterion | Test node id(s) |
|---|---|
| 1. Unauthenticated `/healthz` key set `{"status","now"}`, both token states | `test_receiver_health.py::test_ac01_unauthenticated_healthz_key_set`, `test_ac01_unauthenticated_healthz_key_set_with_auth_configured` |
| 2. Authorized `/healthz` detail fields correct against a seeded store | `test_receiver_health.py::test_ac02_authorized_healthz_has_correct_detail_fields` |
| 3. Wrong bearer token -> liveness-only body, status 200 | `test_receiver_health.py::test_ac03_wrong_token_gets_liveness_only_status_200` |
| 4. Unauthenticated body leaks no token substring | `test_receiver_health.py::test_ac04_unauthenticated_body_has_no_token_substring` |
| 5. Empty store: `last_ingest_at`/`stale_seconds` both null | `test_receiver_health.py::test_ac05_empty_store_null_last_ingest_and_stale_seconds` |
| 6. 3h-old row -> `stale_seconds`~10800; future row clamped to 0 | `test_receiver_health.py::test_ac06_stale_seconds_3h_old_and_future_clamped_to_zero` |
| 7. `last_otlp_ingest_at` ignores newer transcript row | `test_receiver_health.py::test_ac07_otlp_stale_ignores_newer_transcript_row` |
| 8. `GET` to other paths -> 404 | `test_receiver_health.py::test_ac08_get_other_paths_404` (parametrized, 3 cases) |
| 9. Store error -> 503 degraded, no leak | `test_receiver_health.py::test_ac09_store_error_yields_503_degraded_no_leak` |
| 10. `cli` rejected `session_has_otlp`, both table shapes, counts unchanged | `test_receiver_health.py::test_ac10_cli_rejected_when_session_has_token_usage_otlp_row`, `test_ac10_cli_rejected_when_session_has_only_cost_usage_otlp_row` |
| 11/12. Backfill entrypoint accepted, stored verbatim | `test_receiver_health.py::test_ac11_ac12_backfill_entrypoint_accepted_and_stored_verbatim` (parametrized, 2 cases) |
| 13. Quarantine boundary: 60s rejected `too_recent`, 2h accepted | `test_receiver_health.py::test_ac13_quarantine_boundary_too_recent_then_accepted` |
| 14. Desktop exempt from both checks, asserted positively | `test_receiver_health.py::test_ac14_desktop_exempt_from_otlp_check_and_quarantine` |
| 15. Out-of-set entrypoint still `invalid_entrypoint` | `test_receiver_health.py::test_ac15_out_of_set_entrypoint_still_rejects_invalid_entrypoint` |
| 16. `sessions_with_otlp_rows` called once, arg not None, all `str` | `test_receiver_health.py::test_ac16_sessions_with_otlp_rows_called_once_with_str_ids` |
| 17. Mixed batch: cli rejected, desktop inserted, same session | `test_receiver_health.py::test_ac17_mixed_batch_cli_rejected_desktop_inserted_same_session` |
| 18. Only the four named pre-existing tests broken (documented) | `test_receiver_health.py::test_ac18_only_the_four_named_preexisting_tests_are_inverted` |
| 19. `/healthz` opens no new connection while a POST is possible | `test_receiver_health.py::test_ac19_healthz_does_not_open_a_new_connection` |
| 20. Whitespace-padded session id still excludes, verbatim | `test_receiver_health.py::test_ac20_whitespace_padded_session_id_still_excludes` |
| 21. Type-conversion class (`true`/`1e20`) rejected `invalid_session_id`, not double-billed | `test_receiver_health.py::test_ac21_non_str_session_id_rejected_not_double_billed` (parametrized, 2 cases) |

## Task 04 — `04-sweeper-cli-backfill.md`

| Criterion | Test node id(s) |
|---|---|
| 1. `cli` transcript aged 2h ships `entrypoint=="cli"` | `test_cli_backfill.py::test_04_ac01_cli_transcript_aged_2h_ships_with_entrypoint_cli` |
| 2. Same fixture aged 60s produces no record | `test_cli_backfill.py::test_04_ac02_cli_transcript_aged_60s_produces_no_record` |
| 3. THE TRAP: withhold state, then ships after the window | `test_cli_backfill.py::test_04_ac03_quarantine_withholds_state_then_ships_after_window` |
| 4. `claude-desktop` aged 60s still ships | `test_cli_backfill.py::test_04_ac04_desktop_aged_60s_still_ships` |
| 5. Missing entrypoint: no record, no raise, marked resolved | `test_cli_backfill.py::test_04_ac05_missing_entrypoint_no_record_no_raise_marked_resolved` |
| 6. Out-of-set entrypoint: no record, IS resolved | `test_cli_backfill.py::test_04_ac06_out_of_set_entrypoint_no_record_is_resolved` |
| 7. Mixed root ships exactly 2 with expected entrypoints | `test_cli_backfill.py::test_04_ac07_mixed_root_ships_exactly_two_expected_entrypoints` |
| 8. Malformed timestamp: no raise, other sessions still ship | `test_cli_backfill.py::test_04_ac08_malformed_timestamp_no_raise_other_sessions_ship` |
| 9. Exit code 0 on every path, including read-only state dir | `test_cli_backfill.py::test_04_ac09_exit_zero_including_read_only_state_dir` |
| 10. The two copies are byte-identical | `test_cli_backfill.py::test_04_ac10_client_and_deploy_copies_are_byte_identical` |
| 11. Client-package hook parses as valid Python | `test_cli_backfill.py::test_04_ac11_client_package_hook_parses_as_valid_python` |
| 12. `too_recent` non-resolving; `session_has_otlp` resolving | `test_cli_backfill.py::test_04_ac12_too_recent_non_resolving_session_has_otlp_resolving` |
| 13. Replay runs once, actually re-scans | `test_cli_backfill.py::test_04_ac13_replay_runs_once_and_actually_rescans` |
| 14. Replay crash-safe: flag persists, remainder still ships | `test_cli_backfill.py::test_04_ac14_replay_is_crash_safe_flag_persists_and_remainder_ships` |
| 15. Replay does not bypass quarantine/entrypoint filter | `test_cli_backfill.py::test_04_ac15_replay_does_not_bypass_quarantine_or_entrypoint_filter` |
| 16. Recovery reported; `shipped` counts only accepted | `test_cli_backfill.py::test_04_ac16_recovery_reported_shipped_counts_only_accepted` |
| 17. Desktop replay reshipping does not duplicate rows (token + cost) | `test_cli_backfill.py::test_04_ac17_desktop_replay_reshipping_does_not_duplicate_rows` |
| 18. Only the two named pre-existing hook tests broken (documented) | `test_cli_backfill.py::test_04_ac18_only_the_two_named_hook_tests_are_inverted` |
| 19. Pre-installation history excluded, even on replay | `test_cli_backfill.py::test_04_ac19_pre_installation_history_excluded_even_on_replay` |

## Task 06 — `06-otlp-session-id-coercion.md`

| Criterion | Test node id(s) |
|---|---|
| 1. `doubleValue 1e20` / `boolValue true` now exclude correctly | `test_receiver_health.py::test_06_ac01_double_1e20_and_bool_true_now_exclude_correctly` (parametrized, 2 cases) |
| 2. Four already-correct wrappers stay correct; absent -> `unknown` | `test_receiver_health.py::test_06_ac02_already_correct_wrappers_stay_correct` (parametrized, 3 cases), `test_06_ac02_absent_session_id_stores_unknown` |
| 3. `typeof(session_id)=='text'`, equals `str(python value)` for all 9 wrappers | `test_receiver_health.py::test_06_ac03_typeof_session_id_is_text_and_equals_str_python_value` (parametrized, 5 cases) |
| 4. `dp_key` unchanged by coercion; dedupe intact | `test_receiver_health.py::test_06_ac04_dp_key_unchanged_by_coercion_and_dedupe_intact` |
| 5. Ordinary UUID session is byte-identical to the pre-fix value | `test_receiver_health.py::test_06_ac05_ordinary_uuid_session_is_byte_identical_to_prefix_value` |
| 6. Absent/falsy `session.id` still stores `unknown` | `test_receiver_health.py::test_06_ac06_falsy_or_absent_session_id_stores_unknown` (parametrized, 3 cases) |
| 7. `user_email={"a":1}` still `store_error:ProgrammingError` (new test, per orchestrator correction) | `test_receiver_health.py::test_06_ac07_user_email_dict_still_raises_programming_error` |
| 8. Targeted five-file selection: 8 failed / 166 passed, all owned by task 05 | Property of the full targeted run (see this task's completion report); the eight are inverted in `test_transcript.py`, `test_receiver.py`, `test_transcript_hook.py`, `test_integration_desktop.py` per the seven-hunk list above. |
| 9. `git diff` on `receiver.py` confined to `_common` plus comments | `test_receiver_health.py::test_06_ac09_other_ingest_paths_unaffected_by_common_coercion` (behavioral confinement -- a byte-level `git diff` isolation needs the pre-task-06 scratchpad snapshot, not available to a durable checked-in test; see the test's own docstring) |

## GAPs (explicit)

Criterion 03.18's and 04.18's "list every pre-existing test your change breaks" are
documentation properties, not independently re-derivable by a unit test -- both are
represented above by a lightweight pin test that checks the expected test names/negative
cases are present, per this goal's context package. Task 06 criterion 8 (the targeted
five-file failure count) is a command-output property of the full run, not a single node
id, consistent with how other command-output criteria are handled elsewhere in this file.
