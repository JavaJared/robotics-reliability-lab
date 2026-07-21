"""Shared dependency-free HTTP client."""

from __future__ import annotations

import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def request_json(
    base_url: str,
    method: str,
    path: str,
    body: dict[str, Any] | None = None,
    token: str = "demo-robot-token",
    admin: bool = False,
    timeout: float = 5,
) -> tuple[int, dict[str, Any]]:
    data = json.dumps(body).encode() if body is not None else None
    headers = {
        "Content-Type": "application/json",
        "X-Admin-Token" if admin else "X-Robot-Token": token,
    }
    request = Request(base_url.rstrip("/") + path, data=data, headers=headers, method=method)
    try:
        with urlopen(request, timeout=timeout) as response:
            raw = response.read()
            return response.status, json.loads(raw) if raw else {}
    except HTTPError as exc:
        raw = exc.read()
        return exc.code, json.loads(raw) if raw else {}
    except URLError as exc:
        return 0, {"error": str(exc.reason)}
