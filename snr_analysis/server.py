from __future__ import annotations

import mimetypes
import threading
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from .config import (
    DEFAULT_DATA_ROOT,
    DEFAULT_EXPERIMENT,
    DEFAULT_HIGHPASS_CUTOFF_HZ,
    DEFAULT_NORMALIZATION_METHOD,
    DEFAULT_SNR_BIN_SECONDS,
    DEFAULT_SNR_PADDING_AFTER,
    DEFAULT_SNR_PADDING_BEFORE,
    PLOT_POINT_LIMIT,
    STATIC_DIR,
)
from .folders import browse_folder
from .http_utils import error_response, json_response, parse_path
from .snr import calculate_snr_payload, get_snr_methods
from .traces import get_experiment_trace_info, load_trace_payload


class SNRRequestHandler(BaseHTTPRequestHandler):
    def log_message(self, format: str, *args: Any) -> None:
        return

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)

        try:
            if parsed.path == "/":
                self.serve_static(STATIC_DIR / "index.html")
            elif parsed.path.startswith("/static/"):
                self.serve_static(STATIC_DIR / parsed.path.removeprefix("/static/"))
            elif parsed.path == "/vendor/plotly.min.js":
                self.serve_plotly()
            elif parsed.path == "/api/defaults":
                json_response(
                    self,
                    {
                        "data_root": str(DEFAULT_DATA_ROOT),
                        "default_experiment": str(DEFAULT_EXPERIMENT),
                        "snr_methods": get_snr_methods(),
                        "default_snr_padding_before": DEFAULT_SNR_PADDING_BEFORE,
                        "default_snr_padding_after": DEFAULT_SNR_PADDING_AFTER,
                        "default_snr_bin_seconds": DEFAULT_SNR_BIN_SECONDS,
                        "default_highpass_cutoff_hz": DEFAULT_HIGHPASS_CUTOFF_HZ,
                    },
                )
            elif parsed.path == "/api/browse":
                path = parse_path(query.get("path", [None])[0], DEFAULT_DATA_ROOT)
                json_response(self, browse_folder(path))
            elif parsed.path == "/api/experiment":
                path = parse_path(query.get("experiment_path", [None])[0], DEFAULT_EXPERIMENT)
                json_response(self, get_experiment_trace_info(path))
            elif parsed.path == "/api/traces":
                path = parse_path(query.get("experiment_path", [None])[0], DEFAULT_EXPERIMENT)
                trace_key = query.get("trace_type", ["raw"])[0]
                roi = query.get("roi", query.get("selection", ["all"]))[0]
                normalize = query.get("normalize", ["false"])[0].lower() == "true"
                normalization_method = query.get("normalization_method", [DEFAULT_NORMALIZATION_METHOD])[0]
                show_spikes = query.get("show_spikes", ["true"])[0].lower() == "true"
                offset = float(query.get("offset", ["1.35"])[0])
                start_frame = int(query.get("start_frame", ["0"])[0])
                highpass_cutoff_hz = float(query.get("highpass_cutoff_hz", [str(DEFAULT_HIGHPASS_CUTOFF_HZ)])[0])
                payload = load_trace_payload(
                    path,
                    trace_key,
                    roi,
                    PLOT_POINT_LIMIT,
                    normalize,
                    normalization_method,
                    show_spikes,
                    start_frame,
                    highpass_cutoff_hz,
                    offset,
                )
                json_response(self, payload)
            elif parsed.path == "/api/snr":
                path = parse_path(query.get("experiment_path", [None])[0], DEFAULT_EXPERIMENT)
                trace_key = query.get("trace_type", ["mcsf"])[0]
                roi = query.get("roi", ["all"])[0]
                method = query.get("method", ["basic"])[0]
                signal_source = query.get("signal_source", ["both"])[0]
                highpass_cutoff_hz = float(query.get("highpass_cutoff_hz", [str(DEFAULT_HIGHPASS_CUTOFF_HZ)])[0])
                padding_before = int(query.get("padding_before", [str(DEFAULT_SNR_PADDING_BEFORE)])[0])
                padding_after = int(query.get("padding_after", [str(DEFAULT_SNR_PADDING_AFTER)])[0])
                start_frame = int(query.get("start_frame", ["0"])[0])
                bin_seconds = float(query.get("bin_seconds", [str(DEFAULT_SNR_BIN_SECONDS)])[0])
                json_response(
                    self,
                    calculate_snr_payload(
                        path,
                        trace_key,
                        roi,
                        method,
                        signal_source,
                        highpass_cutoff_hz,
                        padding_before,
                        padding_after,
                        start_frame,
                        bin_seconds,
                    ),
                )
            else:
                error_response(self, "Not found", HTTPStatus.NOT_FOUND)
        except Exception as exc:
            error_response(self, str(exc), HTTPStatus.BAD_REQUEST)

    def serve_static(self, path: Path) -> None:
        resolved_path = path.resolve()
        resolved_static = STATIC_DIR.resolve()
        if not resolved_path.is_file() or (resolved_path != resolved_static and resolved_static not in resolved_path.parents):
            error_response(self, "Not found", HTTPStatus.NOT_FOUND)
            return

        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        body = path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def serve_plotly(self) -> None:
        import plotly

        plotly_path = Path(plotly.__file__).resolve().parent / "package_data" / "plotly.min.js"
        body = plotly_path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/javascript; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def run_server(host: str = "127.0.0.1", port: int = 8057, open_browser: bool = True) -> None:
    server = ThreadingHTTPServer((host, port), SNRRequestHandler)
    url = f"http://{host}:{port}"
    print(f"SNR Analysis running at {url}")
    print("Press Ctrl+C to stop.")
    if open_browser:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    server.serve_forever()
