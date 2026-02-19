from __future__ import annotations

import datetime as dt
import threading
import time
from email.utils import format_datetime

# Global state for caching the formatted date string to minimize overhead.
# These variables track the current cached second and its corresponding byte representation.
_DATE_CACHE_LOCK = threading.Lock()
_DATE_CACHE_SECOND: int = -1
_DATE_CACHE_VALUE: bytes = b""


def cached_http_date_header() -> bytes:
    """
    Returns an RFC 9110-compliant HTTP date header as a byte string.

    The formatted value is cached on a per-second basis to avoid repeated datetime
    allocations and string formatting operations on high-throughput response paths.
    The function uses a double-checked locking pattern to ensure thread safety
    during cache updates while maintaining performance for the hot path.

    Returns:
        bytes: The current HTTP date in the format 'Day, DD Mon YYYY HH:MM:SS GMT',
            encoded as latin-1 bytes.
    """
    global _DATE_CACHE_SECOND, _DATE_CACHE_VALUE

    # Capture the current epoch time as an integer (granularity of one second)
    current_second = int(time.time())

    # Fast path: check if the cache is still valid for the current second
    if current_second == _DATE_CACHE_SECOND:
        return _DATE_CACHE_VALUE

    # Slow path: acquire lock and regenerate the date string if the second has changed
    with _DATE_CACHE_LOCK:
        # Double-check the condition inside the lock to prevent redundant updates
        if current_second != _DATE_CACHE_SECOND:
            # Generate a UTC-aware datetime object from the current timestamp
            now = dt.datetime.fromtimestamp(current_second, tz=dt.timezone.utc)

            # Format the datetime into an RFC 9110 compliant string and encode to bytes
            _DATE_CACHE_VALUE = format_datetime(now, usegmt=True).encode("latin-1")

            # Update the cached second marker
            _DATE_CACHE_SECOND = current_second

    return _DATE_CACHE_VALUE
