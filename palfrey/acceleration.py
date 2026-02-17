"""Rust-accelerated helpers with pure-Python fallbacks.

The extension is optional. Palfrey always remains functional without native
code, but uses Rust implementations when available for parsing hot paths.
"""

from __future__ import annotations

from collections.abc import Sequence

try:
    from palfrey_rust import (
        parse_header_items as _parse_header_items,
        parse_request_head as _parse_request_head,
        split_csv_values as _split_csv_values,
    )

    HAS_RUST_EXTENSION = True
except ImportError:  # pragma: no cover - executed when Rust extension is absent.
    _parse_header_items = None
    _parse_request_head = None
    _split_csv_values = None
    HAS_RUST_EXTENSION = False


class HeaderParseError(ValueError):
    """Raised when a header entry does not conform to ``name:value`` syntax."""


def parse_header_items(headers: Sequence[str]) -> list[tuple[str, str]]:
    """Parse ``name:value`` header strings.

    Args:
        headers: Header entries, typically provided through CLI `--header`.

    Returns:
        Parsed and trimmed header tuples.

    Raises:
        HeaderParseError: If any header does not contain a colon separator.
    """

    if not headers:
        return []

    if HAS_RUST_EXTENSION:
        try:
            return list(_parse_header_items(list(headers)))
        except ValueError as exc:  # pragma: no cover - rust-only path.
            raise HeaderParseError(str(exc)) from exc

    parsed: list[tuple[str, str]] = []
    for item in headers:
        name, separator, value = item.partition(":")
        if not separator:
            raise HeaderParseError(f"Invalid header '{item}'. Expected 'name:value'.")
        parsed.append((name.strip(), value.lstrip()))
    return parsed


def split_csv_values(value: str) -> list[str]:
    """Split and normalize comma-separated values.

    Args:
        value: Comma-separated string.

    Returns:
        List of trimmed, non-empty values.
    """

    if HAS_RUST_EXTENSION:
        return list(_split_csv_values(value))
    return [segment.strip() for segment in value.split(",") if segment.strip()]


def parse_request_head(data: bytes) -> tuple[str, str, str, list[tuple[str, str]]]:
    """Parse raw HTTP request head bytes.

    Args:
        data: Raw bytes up to and including the CRLFCRLF delimiter.

    Returns:
        A tuple of ``(method, target, version, headers)``.

    Raises:
        ValueError: If the payload cannot be parsed as a valid HTTP request head.
    """

    if HAS_RUST_EXTENSION:
        return _parse_request_head(data)

    try:
        decoded = data.decode("latin-1")
    except UnicodeDecodeError as exc:
        raise ValueError("Request head is not valid latin-1 data") from exc

    lines = decoded.split("\r\n")
    if not lines or not lines[0]:
        raise ValueError("Missing request line")

    request_line_parts = lines[0].split(" ")
    if len(request_line_parts) != 3:
        raise ValueError("Invalid request line")

    method, target, version = request_line_parts
    headers: list[tuple[str, str]] = []
    for line in lines[1:]:
        if not line:
            break
        name, separator, value = line.partition(":")
        if not separator:
            raise ValueError(f"Malformed header line: {line!r}")
        headers.append((name.strip(), value.lstrip()))

    return method, target, version, headers
