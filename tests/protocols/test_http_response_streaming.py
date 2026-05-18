from __future__ import annotations

from palfrey.config import PalfreyConfig
from palfrey.protocols.http import HTTPResponse, encode_http_response, encode_http_response_chunks
from palfrey.server import PalfreyServer


class _Writer:
    def __init__(self) -> None:
        self.write_calls: list[bytes] = []
        self.writelines_calls: list[list[bytes]] = []

    def write(self, data: bytes) -> None:
        self.write_calls.append(data)

    def writelines(self, data) -> None:
        self.writelines_calls.append(list(data))

    async def drain(self) -> None:
        return None


def test_encode_http_response_chunks_small_body_roundtrip() -> None:
    response = HTTPResponse(
        status=200,
        headers=[(b"content-type", b"text/plain")],
        body_chunks=[b"ok"],
    )

    streamed = list(encode_http_response_chunks(response, keep_alive=True))
    assert b"".join(streamed) == encode_http_response(response, keep_alive=True)


def test_encode_http_response_chunks_large_body_preserves_chunk_reference() -> None:
    body = b"x" * 70_000
    response = HTTPResponse(
        status=200,
        headers=[(b"content-type", b"application/octet-stream")],
        body_chunks=[body],
    )

    streamed = list(encode_http_response_chunks(response, keep_alive=True))

    assert any(part is body for part in streamed)
    assert b"".join(streamed) == encode_http_response(response, keep_alive=True)


def test_encode_http_response_chunks_empty_204_body() -> None:
    response = HTTPResponse(status=204, headers=[], body_chunks=[])

    payload = b"".join(encode_http_response_chunks(response, keep_alive=True))

    assert b"content-length: 0" in payload.lower()
    assert payload.endswith(b"\r\n\r\n")


def test_encode_http_response_chunks_chunked_frames_are_individual_parts() -> None:
    response = HTTPResponse(
        status=200,
        headers=[(b"transfer-encoding", b"chunked")],
        body_chunks=[b"abc", b"def"],
        chunked_encoding=True,
    )

    streamed = list(encode_http_response_chunks(response, keep_alive=True))

    assert streamed[-7:] == [b"3\r\n", b"abc", b"\r\n", b"3\r\n", b"def", b"\r\n", b"0\r\n\r\n"]


def test_write_response_streams_with_writelines_and_preserves_keep_alive_header() -> None:
    async def scenario() -> None:
        server = PalfreyServer(PalfreyConfig(app="tests.fixtures.apps:http_app"))
        writer = _Writer()
        body = b"x" * 70_000
        response = HTTPResponse(
            status=200,
            headers=[(b"content-type", b"application/octet-stream")],
            body_chunks=[body],
        )

        await server._write_response(writer, response, keep_alive=False)  # type: ignore[arg-type]

        assert writer.write_calls == []
        assert len(writer.writelines_calls) == 1
        streamed = writer.writelines_calls[0]
        assert any(part is body for part in streamed)
        assert b"connection: close\r\n" in b"".join(streamed).lower()

    import asyncio

    asyncio.run(scenario())
