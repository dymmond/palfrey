# Task 3b — server.py Coverage Improvement

## Coverage Before

```text
Name                  Stmts   Miss  Cover   Missing
--------------------------------------------------
palfrey/server.py      645     93    83%   71, 75-84, 93, 227-230, 245-247, 271-272, 292-293, 312-316, 325, 355-359, 367, 402-403, 485, 489, 542, 559, 569-570, 573, 664-667, 678, 698, 722, 726, 730-734, 739, 745, 803-804, 809, 816-820, 827-831, 842, 933, 960, 1023-1040, 1062-1063, 1066, 1076, 1086, 1088, 1090, 1092, 1099-1127, 1137, 1238, 1244, 1248, 1254
```

## Tests Added

New file: `tests/server/test_server_edge_cases.py`

- `test_capture_signals_on_non_main_thread_skips_signal_handlers`
- `test_shutdown_ignores_noncallable_server_close_and_wait_closed`
- `test_handle_connection_returns_early_when_app_not_resolved`
- `test_handle_connection_returns_503_when_request_slot_not_acquired`
- `test_queue_with_backpressure_pauses_and_resumes_reader`
- `test_pause_resume_reader_handle_missing_transport_and_transport_errors`
- `test_log_running_messages_without_sockets_supports_uds_and_ipv6_host`
- `test_format_running_target_handles_error_and_non_tuple_values`
- `test_handle_http_request_raises_when_application_unresolved`
- `test_http2_request_handler_handles_failures_and_shutdown_threshold`
- `test_http2_request_handler_returns_503_for_concurrency_guards`
- `test_serve_http3_rejects_unsupported_modes`
- `test_serve_http3_request_handler_covers_guard_and_error_paths`
- `test_serve_http3_requires_resolved_app`
- `test_loop_backend_name_custom_class_string`

## Coverage After

Command:

```bash
hatch run test:test --cov palfrey/server.py --cov-report=term-missing
```

```text
Name                  Stmts   Miss Branch BrPart  Cover   Missing
-----------------------------------------------------------------
palfrey/server.py      645     30    246     23    94%   71, 75-84, 93, 133, 227->230, 245-247, 271-272, 292-293, 312-316, 325, 355-359, 367->365, 559->562, 569-570, 573->575, 678->680, 698->700, 726, 933->exit, 960, 1032->1034, 1120, 1121->1127, 1238, 1244->1253, 1248->1250, 1254->exit
```

Improvement: **83% → 94%** (**+11 points**)
