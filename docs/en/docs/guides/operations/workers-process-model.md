# Workers and Process Model

## Enable workers

```bash
palfrey myapp.main:app --workers 4
```

## Behavior

- Master process supervises child workers.
- Dead workers are replaced.
- `--reload` and `--workers` cannot be combined.
- Worker mode requires an app import string.
