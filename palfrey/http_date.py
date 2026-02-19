"""Cached HTTP date header generation utilities."""

from __future__ import annotations

import datetime as dt
import threading
import time
from email.utils import format_datetime

_DATE_CACHE_LOCK = threading.Lock()
_DATE_CACHE_SECOND = -1
_DATE_CACHE_VALUE = b""


def cached_http_date_header() -> bytes:
    """Return RFC 9110-compliant HTTP date header bytes.

    The formatted value is cached per-second to avoid repeated datetime
    allocations on high-throughput response paths.
    """

    global _DATE_CACHE_SECOND, _DATE_CACHE_VALUE

    current_second = int(time.time())
    if current_second == _DATE_CACHE_SECOND:
        return _DATE_CACHE_VALUE

    with _DATE_CACHE_LOCK:
        if current_second != _DATE_CACHE_SECOND:
            now = dt.datetime.fromtimestamp(current_second, tz=dt.timezone.utc)
            _DATE_CACHE_VALUE = format_datetime(now, usegmt=True).encode("latin-1")
            _DATE_CACHE_SECOND = current_second

    return _DATE_CACHE_VALUE
