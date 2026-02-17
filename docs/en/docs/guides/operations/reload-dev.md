# Reload and Development

## Enable reload

```bash
palfrey myapp.main:app --reload
```

## Watch controls

- `--reload-dir`
- `--reload-include`
- `--reload-exclude`
- `--reload-delay`

Palfrey's reload supervisor performs polling-based file change detection and restarts a child server process.
