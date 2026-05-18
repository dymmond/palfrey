"""Low-level ASGI protocol implementations for HTTP/1.1, HTTP/2, HTTP/3, and WebSocket.

This package provides protocol-specific handlers that parse incoming bytes into ASGI
events and encode outgoing events into wire bytes. It includes HTTP/1.1 request parsing
with httptools, HTTP/2 stream multiplexing, HTTP/3 QUIC support, and WebSocket frame
handling. Each protocol handler implements the run_asgi-style function signature.
"""
