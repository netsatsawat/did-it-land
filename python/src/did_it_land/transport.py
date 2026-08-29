"""Transport boundary for http capsules.

The runtime builds a provider-relative request from a capsule and hands it to a
Transport. Keeping the transport injectable is what lets the same reconcile path run
against a real vendor, against a local emulator, or against an in-process fake with no
network and no keys. Base URL and auth are the transport's concern, never the corpus.
"""

from __future__ import annotations

import json as _json
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from .capsule import Request


class TransportError(RuntimeError):
    """The service could not be reached or did not answer in time.

    A transport that raises this tells reconcile and unwind that the question went
    unanswered, which is an unknown outcome, not a no. Custom transports should
    raise it for timeouts and connection failures."""


@dataclass(frozen=True)
class Response:
    status_code: int
    body: object = None
    headers: dict[str, str] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return 200 <= self.status_code < 300


@runtime_checkable
class Transport(Protocol):
    def send(self, request: Request) -> Response:
        ...


class HttpxTransport:
    """Default transport backed by httpx.

    Configured per provider with a base URL and any auth headers. httpx is imported
    lazily so importing did-it-land never requires it when a caller brings its own
    transport or only uses the offline paths.
    """

    def __init__(
            self,
            base_url: str,
            headers: dict[str, str] | None = None,
            timeout: float = 15.0):
        self.base_url = base_url.rstrip("/")
        self.headers = dict(headers or {})
        self.timeout = timeout

    def send(self, request: Request) -> Response:
        import httpx

        url = self.base_url + request.path
        merged = {**self.headers, **request.headers}
        try:
            resp = httpx.request(
                request.method,
                url,
                params=request.query or None,
                headers=merged or None,
                timeout=self.timeout)
        except httpx.TransportError as exc:
            raise TransportError(f"{request.method} {url}: {exc}") from exc
        body: object
        try:
            body = resp.json()
        except (ValueError, _json.JSONDecodeError):
            body = resp.text
        return Response(status_code=resp.status_code, body=body, headers=dict(resp.headers))
