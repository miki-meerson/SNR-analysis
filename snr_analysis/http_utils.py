from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from typing import Any
from urllib.parse import unquote


def json_response(handler: BaseHTTPRequestHandler, payload: Any, status: int = 200) -> None:
    body = json.dumps(payload, allow_nan=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def error_response(handler: BaseHTTPRequestHandler, message: str, status: int = 400) -> None:
    json_response(handler, {"error": message}, status)


def parse_path(value: str | None, default: Path | None = None) -> Path:
    if not value:
        if default is None:
            raise ValueError("Missing path")
        return default
    return Path(unquote(value)).expanduser()

