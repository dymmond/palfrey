# Task 17: JSON Output Evidence

## Command
```bash
python -m benchmarks.run --http-requests 10000 --http-concurrency 10 --ws-clients 0 --enable-phases --output /tmp/bench.json
```

## JSON Structure Validation
```bash
python -c "import json; d=json.load(open('/tmp/bench.json')); print('Keys:', list(d.keys())); print('Metadata keys:', list(d['metadata'].keys())); print('Results keys:', list(d['results'].keys()))"
```

**Output:**
```
Keys: ['metadata', 'results']
Metadata keys: ['python_version', 'os', 'cpu', 'loop_type']
Results keys: ['uvicorn', 'palfrey']
```

## Full JSON Output
```json
{
    "metadata": {
        "python_version": "3.14.3",
        "os": "Darwin",
        "cpu": "arm",
        "loop_type": "asyncio"
    },
    "results": {
        "uvicorn": {
            "http": {
                "operations": 10000,
                "duration_seconds": 0.293701417002012,
                "ops_per_second": 34048.18438424999
            },
            "websocket": null
        },
        "palfrey": {
            "http": {
                "operations": 10000,
                "duration_seconds": 0.2917901670007268,
                "ops_per_second": 34271.202840002115
            },
            "websocket": null
        }
    }
}
```

## Verification
✅ JSON file created successfully
✅ Valid JSON structure
✅ Contains metadata (python_version, os, cpu, loop_type)
✅ Contains results for both servers
✅ HTTP results include operations, duration_seconds, ops_per_second
