# Reload and Development

Palfrey includes a polling reloader with include/exclude pattern controls.

```python
{!> ../../../docs_src//reload/reload_cli.py !}
```

## Source mapping

- Uvicorn source: `uvicorn/supervisors/statreload.py`
- Uvicorn source: `uvicorn/supervisors/watchfilesreload.py`
- Uvicorn source: `uvicorn/supervisors/basereload.py`
