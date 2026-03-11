## Task 13 - Scenario 1: Backpressure engages under load

- Command used:
  - `hatch run python -m palfrey qa_large_stream_app:app --host 127.0.0.1 --port 18907`
  - `curl -sS http://127.0.0.1:18907 -o /tmp/palfrey-task13-stream.bin`
- Result:
  - `curl_exit=0`
  - Downloaded bytes: `10485760` (10 MiB)
- Evidence interpretation:
  - Large chunked streaming response completed successfully under load.
  - No crash/OOM observed during transfer.
