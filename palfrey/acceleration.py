from __future__ import annotations

from collections.abc import Callable, Sequence

ParseHeaderItemsFn = Callable[[list[str]], list[tuple[str, str]]]
ParseRequestHeadFn = Callable[[bytes], tuple[str, str, str, list[tuple[str, str]]]]
SplitCSVValuesFn = Callable[[str], list[str]]
WebSocketPayloadBuffer = bytes | bytearray | memoryview
UnmaskWebSocketPayloadFn = Callable[[WebSocketPayloadBuffer, bytes], bytes]

# Placeholders for the Rust extension functions
_parse_header_items: ParseHeaderItemsFn | None = None
_parse_request_head: ParseRequestHeadFn | None = None
_split_csv_values: SplitCSVValuesFn | None = None
_unmask_websocket_payload: UnmaskWebSocketPayloadFn | None = None

try:
    from palfrey_rust import (
        parse_header_items as _parse_header_items,
        parse_request_head as _parse_request_head,
        split_csv_values as _split_csv_values,
        unmask_websocket_payload as _unmask_websocket_payload,
    )

    HAS_RUST_EXTENSION = True
except ImportError:
    HAS_RUST_EXTENSION = False


class HeaderParseError(ValueError):
    """
    Exception raised when a header entry fails to conform to the expected 'name:value' format.

    This error typically occurs during the manual parsing of header sequences when the
    required colon separator is missing from an input string.
    """


def parse_header_items(headers: Sequence[str]) -> list[tuple[str, str]]:
    """
    Parses a sequence of raw header strings into a list of key-value tuples.

    Each string in the input sequence is expected to be in the format 'name:value'. The
    function trims whitespace from the name and leading whitespace from the value.

    Args:
        headers (Sequence[str]): A sequence of header strings, such as those provided via
            command-line interfaces.

    Returns:
        list[tuple[str, str]]: A list of tuples where the first element is the stripped
            header name and the second is the left-stripped header value.

    Raises:
        HeaderParseError: If a header string does not contain the mandatory colon separator.
    """
    if not headers:
        return []

    # Attempt to use the Rust-accelerated implementation if available for performance
    if HAS_RUST_EXTENSION and _parse_header_items is not None:
        try:
            return list(_parse_header_items(list(headers)))
        except ValueError as exc:
            raise HeaderParseError(str(exc)) from exc

    parsed: list[tuple[str, str]] = []
    for item in headers:
        # Partition splits the string at the first occurrence of the separator
        name, separator, value = item.partition(":")
        if not separator:
            raise HeaderParseError(f"Invalid header '{item}'. Expected 'name:value'.")
        parsed.append((name.strip(), value.lstrip()))
    return parsed


def split_csv_values(value: str) -> list[str]:
    """
    Splits a comma-separated string into a list of individual, normalized values.

    This function removes surrounding whitespace from each segment and filters out any
    resulting empty strings to ensure a clean list of values.

    Args:
        value (str): The raw comma-separated string to be processed.

    Returns:
        list[str]: A list of non-empty, trimmed strings extracted from the input.
    """
    if HAS_RUST_EXTENSION and _split_csv_values is not None:
        return list(_split_csv_values(value))

    # Fallback to pure-Python list comprehension for splitting and stripping
    return [segment.strip() for segment in value.split(",") if segment.strip()]


def parse_request_head(data: bytes) -> tuple[str, str, str, list[tuple[str, str]]]:
    """
    Parses raw HTTP request head bytes into structured components.

    Processes the initial request line and subsequent headers. The input data should
    ideally contain the full header block ending with the standard CRLFCRLF delimiter.

    Args:
        data (bytes): The raw byte sequence representing the HTTP request head.

    Returns:
        tuple[str, str, str, list[tuple[str, str]]]: A four-element tuple containing
            (method, target, version, headers), where headers is a list of name-value pairs.

    Raises:
        ValueError: If the request line is missing, malformed, or if any header line is
            not correctly formatted.
    """
    if HAS_RUST_EXTENSION and _parse_request_head is not None:
        return _parse_request_head(data)

    # Use latin-1 decoding to preserve the original byte values as per HTTP specs
    decoded = data.decode("latin-1")

    lines = decoded.split("\r\n")
    if not lines or not lines[0]:
        raise ValueError("Missing request line")

    request_line_parts = lines[0].split(" ")
    if len(request_line_parts) != 3:
        raise ValueError("Invalid request line")

    method, target, version = request_line_parts
    headers: list[tuple[str, str]] = []

    # Iterate through lines following the request line
    for line in lines[1:]:
        if not line:
            break
        name, separator, value = line.partition(":")
        if not separator:
            raise ValueError(f"Malformed header line: {line!r}")
        headers.append((name.strip(), value.lstrip()))

    return method, target, version, headers


def unmask_websocket_payload(payload: WebSocketPayloadBuffer, masking_key: bytes) -> bytes:
    """
    Applies the WebSocket XOR masking algorithm to a payload.

    WebSockets require client-to-server frames to be masked using a 4-byte key. This
    function reverses that mask to retrieve the original data (or applies it).

    Args:
        payload (WebSocketPayloadBuffer): The masked (or unmasked) payload data buffer.
        masking_key (bytes): A 4-byte byte string used as the XOR masking key.

    Returns:
        bytes: The resulting transformed byte string.

    Raises:
        ValueError: If the provided masking_key is not exactly 4 bytes in length.
    """
    if len(masking_key) != 4:
        raise ValueError("WebSocket masking key must be exactly 4 bytes")

    if HAS_RUST_EXTENSION and _unmask_websocket_payload is not None:
        return _unmask_websocket_payload(payload, masking_key)

    # Manual XOR application for pure-Python fallback
    m0, m1, m2, m3 = masking_key
    output = bytearray(payload)
    length = len(output)
    index = 0

    # Process bytes in 4-byte chunks for a slight performance boost in Python
    while index + 4 <= length:
        output[index] ^= m0
        output[index + 1] ^= m1
        output[index + 2] ^= m2
        output[index + 3] ^= m3
        index += 4

    # Handle remaining bytes (less than 4) if the payload length is not a multiple of 4
    if index < length:
        output[index] ^= m0
        index += 1
    if index < length:
        output[index] ^= m1
        index += 1
    if index < length:
        output[index] ^= m2

    return bytes(output)
