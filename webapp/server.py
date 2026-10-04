#!/usr/bin/env python3
"""Local web app: serves webapp/static/, the same files the hosted site publishes.

Validation and PDF generation run in the browser, so applicant data never reaches this
server. Start with: python -m webapp
"""

from __future__ import annotations

import argparse
import contextlib
import json
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import unquote, urlsplit

from script.core.paths import TEMPLATE
from script.core.utils import ensure_workspace_dirs
from webapp.build import STATIC, TEMPLATE_URL, site_meta

TYPES = {
    '.html': 'text/html; charset=utf-8',
    '.js': 'text/javascript; charset=utf-8',
    '.mjs': 'text/javascript; charset=utf-8',
    '.css': 'text/css; charset=utf-8',
    '.json': 'application/json; charset=utf-8',
    '.pdf': 'application/pdf',
}
# Matches webapp/static/_headers, which the hosted site uses for the same protection.
SECURITY_HEADERS = {
    'X-Content-Type-Options': 'nosniff',
    'Referrer-Policy': 'no-referrer',
    'Cross-Origin-Resource-Policy': 'same-origin',
    'Cross-Origin-Opener-Policy': 'same-origin',
    'Permissions-Policy': 'camera=(), microphone=(), geolocation=(), payment=(), usb=()',
    'Content-Security-Policy': (
        "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' blob: data:; "
        "connect-src 'self'; worker-src 'self'; object-src 'none'; frame-ancestors 'none'; "
        "base-uri 'none'; form-action 'none'"
    ),
}


class LocalServer(ThreadingHTTPServer):
    """Connections are handled concurrently so an idle browser socket never blocks the app."""

    daemon_threads = True
    # Browsers fetch every JS module in parallel; the default backlog of 5 resets some of them.
    request_queue_size = 64

    def __init__(self, address: tuple[str, int]):
        super().__init__(address, Handler)
        self.origin = f'http://127.0.0.1:{self.server_port}'


class Handler(BaseHTTPRequestHandler):
    server: LocalServer

    def setup(self) -> None:
        super().setup()
        self.connection.settimeout(15)

    def log_message(self, format: str, *args: Any) -> None:
        """Requests are not logged."""

    def send_bytes(self, status: int, data: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        for name, value in SECURITY_HEADERS.items():
            self.send_header(name, value)
        self.end_headers()
        with contextlib.suppress(BrokenPipeError, ConnectionResetError):
            self.wfile.write(data)

    def reply(self, status: int, value: dict) -> None:
        self.send_bytes(status, json.dumps(value).encode(), TYPES['.json'])

    def do_GET(self) -> None:
        # Only the local origin may load the app; this also blocks DNS-rebinding pages.
        origin = self.headers.get('Origin')
        if (
            self.headers.get('Host') != f'127.0.0.1:{self.server.server_port}'
            or (origin and origin != self.server.origin)
            or self.headers.get('Sec-Fetch-Site') == 'cross-site'
        ):
            self.reply(403, {'error': 'Only the local app origin is allowed'})
            return
        route = unquote(urlsplit(self.path).path)
        if route == '/meta.json':
            # Built fresh so local edits show at once; the committed copy is checked by tests.
            self.send_bytes(200, json.dumps(site_meta(), ensure_ascii=False).encode(), TYPES['.json'])
            return
        if route == '/' + TEMPLATE_URL:
            self.send_bytes(200, TEMPLATE.read_bytes(), TYPES['.pdf'])
            return
        target = (STATIC / (route.lstrip('/') or 'index.html')).resolve()
        if (
            not target.is_relative_to(STATIC)
            or not target.is_file()
            or target.suffix not in TYPES
            or any(part.startswith(('.', '_')) for part in target.relative_to(STATIC).parts)
        ):
            self.reply(404, {'error': 'Not found'})
            return
        self.send_bytes(200, target.read_bytes(), TYPES[target.suffix])

    def do_POST(self) -> None:
        self.reply(405, {'error': 'This app has no server-side processing'})


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--open', action='store_true', help='Open the app in your default browser')
    args = parser.parse_args()
    try:
        ensure_workspace_dirs()
        with LocalServer(('127.0.0.1', args.port)) as server:
            print(f'VisaFilla: {server.origin}', flush=True)
            print('Local only. Press Ctrl+C to stop.', flush=True)
            if args.open:
                webbrowser.open(server.origin)
            server.serve_forever()
    except KeyboardInterrupt:
        pass
    except OSError as exc:
        parser.exit(1, f'Cannot start local app: {exc}. Try --port 8766.\n')


if __name__ == '__main__':
    main()
