# TEST REPORT — GOD (2026-09-05)

## Resumo

- **Data:** 2026-09-05T13:39:45Z
- **Commit:** 65a49db
- **Python:** 3.13.14
- **Comando:** `python3 -m unittest tests.test_core -v`
- **Duração:** 8.311s

---

## Resultados

| Metric | Value |
|--------|-------|
| Total | 164 |
| PASS | 164 |
| FAIL | 0 |
| SKIP | 0 |

---

## Testes por Categoria

### Analyzer (3 tests)
- test_coding_is_deep ✅
- test_git ✅
- test_math ✅

### Bench (1 test)
- test_tools_pass_llm_skipped ✅

### CacheHitFormat (1 test)
- test_second_math_does_not_crash ✅

### CacheNorm (1 test)
- test_same_intent ✅

### Dedup (1 test)
- test_same_job_not_duplicated ✅

### Embed (1 test)
- test_paraphrase_closer_than_unrelated ✅

### EvolutionToken (1 test)
- test_observe_sees_zero_llm ✅

### God20P1 (7 tests)
- test_decide_deep_queues_until_worker ✅
- test_decide_fast_tools ✅
- test_decide_normal_direct_or_no_provider ✅
- test_mission_chat_commands ✅
- test_mission_one_active ✅
- test_parent_id_persists_and_ready ✅
- test_provider_stats_kind ✅
- test_sort_adapters_demotes_only_with_n3 ✅

### God20Sprint1 (4 tests)
- test_deep_still_queues ✅
- test_fast_math_skips_vector_and_records_latency ✅
- test_normal_chat_skips_queue ✅
- test_plane_probe_no_fake_board ✅

### GodBuilder (7 tests)
- test_governor_phrase_rejected ✅
- test_master_exists ✅
- test_models_not_invented ✅
- test_overlay_in_prompt ✅
- test_rollback_restores_purpose ✅
- test_subset_gates_execute ✅
- test_unknown_tool_rejected ✅

### Governor (2 tests)
- test_python_ban ✅
- test_root ✅

### NoFakeCompute (1 test)
- test_research_path_depends_on_llm ✅

### OSKernel (10 tests)
- test_admit_ok_when_pressure_low ✅
- test_chat_ps ✅
- test_drivers_not_invented ✅
- test_gpu_optional ✅
- test_kill_queued ✅
- test_priority_claim ✅
- test_ps_measured ✅
- test_syscall_calc ✅
- test_syscall_governor_blocks_passwd ✅
- test_syscall_unknown ✅

### Observer (2 tests)
- test_inspect_real_metrics ✅
- test_tick_edge ✅

### P15Capabilities (6 tests)
- test_can_memory ✅
- test_can_nonexistent ✅
- test_can_voice_false ✅
- test_capabilities_summary ✅
- test_get_capability_memory ✅
- test_list_capabilities ✅

### P15ControlledEvolution (5 tests)
- test_classify_risk_high ✅
- test_classify_risk_low ✅
- test_classify_risk_medium ✅
- test_high_risk_blocked_in_evolution ✅
- test_low_risk_pending_in_evolution ✅

### P15Endpoints (7 tests)
- test_can_endpoint ✅
- test_capabilities_endpoint ✅
- test_health_full_endpoint ✅
- test_liveness_endpoint ✅
- test_readiness_endpoint ✅
- test_system_state_endpoint ✅
- test_traces_endpoint ✅

### P15FeatureFlags (9 tests)
- test_disable_flag ✅
- test_enable_low_risk ✅
- test_flag_risk_classification ✅
- test_flags_disabled_by_default ✅
- test_flags_endpoint ✅
- test_flags_summary ✅
- test_high_risk_blocked_in_strict ✅
- test_list_flags ✅
- test_unknown_flag_rejected ✅

### P15Health (5 tests)
- test_diagnostics ✅
- test_full_health ✅
- test_liveness ✅
- test_readiness ✅
- test_readiness_checks_each_component ✅

### P15RuntimeProtection (9 tests)
- test_brain_py_within_limits ✅
- test_god_object_check ✅
- test_god_object_endpoint ✅
- test_inspect_all ✅
- test_inspect_file ✅
- test_inspect_nonexistent ✅
- test_protection_endpoint ✅
- test_protection_report ✅
- test_runtime_py_resolved ✅

### P15SystemState (5 tests)
- test_system_state_has_providers ✅
- test_system_state_has_queue ✅
- test_system_state_has_resources ✅
- test_system_state_has_runtime ✅
- test_system_state_returns_measured ✅

### P15Trace (4 tests)
- test_record_decision ✅
- test_start_trace ✅
- test_trace_summary ✅
- test_trace_summary_not_found ✅

### P1GraphParallel (3 tests)
- test_claim_allows_two_jobs ✅
- test_graph_reflects_inflight_2 ✅
- test_inflight_cap_returns_2 ✅

### P1RouterReliability (5 tests)
- test_hardcore_mode_claude_first ✅
- test_sort_by_latency_secondary ✅
- test_sort_by_ok_rate_desc ✅
- test_sort_demotes_low_ok_rate ✅
- test_sort_requires_n3 ✅

### Providers (9 tests)
- test_dialogue_is_short_context ✅
- test_format_leads_with_speech ✅
- test_llm_prompt_is_constitution_not_essay ✅
- test_no_fake_scores ✅
- test_openai_message_ignores_reasoning ✅
- test_pick_skips_guard ✅
- test_quem_es_goes_to_llm_path ✅
- test_roadmap_stays_shortcut ✅
- test_web_search_refused ✅

### Qdrant (1 test)
- test_health_embedded ✅

### Queue (2 tests)
- test_claim_complete ✅
- test_claim_respects_inflight_cap ✅

### RepairMemBudget (6 tests)
- test_budget_has_70_90_100 ✅
- test_cache_namespaced_by_god ✅
- test_chat_repara ✅
- test_mem_kinds_isolated ✅
- test_repair_measured ✅
- test_vector_god_filter ✅

### Resources (3 tests)
- test_gpu_optional ✅
- test_heavy_enqueues_when_worker_alive ✅
- test_light_stays_local ✅

### Routing (1 test)
- test_omniroute_probed_down ✅

### SiteBuilder (4 tests)
- test_coding_type_for_site ✅
- test_deny_py_env_core ✅
- test_extract_publish_preview ✅
- test_write_ok ✅

### StaleJob (1 test)
- test_assigned_without_start_requeues ✅

### ThirdEye (7 tests)
- test_criticism_in_pipeline ✅
- test_criticism_ok_for_cache_hit ✅
- test_criticism_passes_for_good_task ✅
- test_criticism_recommends_on_low_score ✅
- test_criticism_warns_on_blocked_deterministic ✅
- test_criticism_warns_on_slow_fast ✅
- test_format_criticism ✅

### TokenIntel (15 tests)
- test_context_efficiency_estimated ✅
- test_cost_split_does_not_mix_subscription_and_api ✅
- test_estimate_is_estimated_not_measured ✅
- test_estimation_error ✅
- test_forecast_unknown_without_history ✅
- test_gate_reuses_firewall ✅
- test_gateway_fallback_flag ✅
- test_langfuse_absent ✅
- test_layout_not_applied_to_this_sandbox ✅
- test_models_unknown_without_llm_samples ✅
- test_pc_node_declared_not_this_host ✅
- test_pricing_unknown ✅
- test_record_zero_actual_on_cache ✅
- test_report_kinds ✅
- test_route_advice_blocks_without_llm ✅

### Tokens (1 test)
- test_tiktoken ✅

### Tools (4 tests)
- test_calc ✅
- test_fs_denied ✅
- test_json ✅

### Validator (10 tests)
- test_coding_cross_validation ✅
- test_fs_write_validation ✅
- test_git_validation ✅
- test_json_validation ✅
- test_llm_empty_fails ✅
- test_llm_nonempty_passes ✅
- test_math_validation_fails_on_error ✅
- test_math_validation_passes ✅
- test_state_validation ✅
- test_validation_in_pipeline ✅

---

## Warnings

1. **ResourceWarning:** unclosed database in sqlite3.Connection (non-critical)
2. **DeprecationWarning:** on_event is deprecated, use lifespan event handlers (FastAPI)

---

## Conclusão

All 164 tests pass. No failures, no skips. System is stable.
