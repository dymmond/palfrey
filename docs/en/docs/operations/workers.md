# Workers and Process Model

Worker mode uses a parent supervisor process that manages child server processes.

## Behavior

- Spawns `N` workers (`--workers`)
- Replaces dead workers
- Handles SIGINT/SIGTERM for coordinated shutdown
- Applies worker health timeout (`--timeout-worker-healthcheck`)

## Source mapping

- Uvicorn source: `uvicorn/supervisors/multiprocess.py`
- Uvicorn source: `uvicorn/supervisors/process.py`
