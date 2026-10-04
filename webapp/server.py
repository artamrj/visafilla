#!/usr/bin/env python3
"""Single-user local web app. Start with: python -m webapp"""

from __future__ import annotations

import argparse
import base64
import contextlib
import json
import re
import secrets
import threading
import time
import webbrowser
from collections import OrderedDict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import pymupdf as fitz
from pydantic import ValidationError

from script.core.renderer import prepare, render_pdf_bytes
from script.core.schema import Applicant
from script.core.utils import ensure_workspace_dirs
from script.core.validator import parse_json_object
from webapp.fields import metadata

MAX_BODY = 3_000_000
ASSETS = {
    '/': ('index.html', 'text/html; charset=utf-8'),
    '/app.js': ('app.js', 'text/javascript; charset=utf-8'),
    '/app.css': ('app.css', 'text/css; charset=utf-8'),
}

# Only application modules are served; filesystem paths are never accepted.
for module in ('helpers', 'state', 'storage', 'rules', 'render', 'api', 'actions', 'country', 'welcome'):
    ASSETS[f'/{module}.js'] = (f'{module}.js', 'text/javascript; charset=utf-8')


def parse_object(text: str) -> dict[str, Any]:
    """Parse JSON without duplicate keys, primitive roots or non-finite numbers."""
    data = parse_json_object(text)

    def bounds(value: Any, depth: int = 0) -> None:
        if depth > 12:
            raise ValueError('JSON nesting is too deep')
        if isinstance(value, str) and len(value) > MAX_BODY:
            raise ValueError('JSON text is too long')
        if isinstance(value, dict):
            if len(value) > 150:
                raise ValueError('Too many JSON properties')
            for child in value.values():
                bounds(child, depth + 1)
        if isinstance(value, list):
            if len(value) > 100:
                raise ValueError('Too many list items')
            for child in value:
                bounds(child, depth + 1)

    bounds(data)
    return data


ERROR_LINKS = [
    ('guardian must', ['personal.date_of_birth', 'application.date', 'guardian.surname']),
    ('date_of_birth must', ['personal.date_of_birth', 'application.date']),
    (
        'expected birth',
        ['personal.date_of_birth', 'passport.date_of_issue', 'application.date', 'journey.arrival_date'],
    ),
    ('passport expires', ['passport.valid_until', 'journey.departure_date']),
    ('fingerprint date must', ['previous_biometrics.date']),
    ('residence permit expires', ['residence.valid_until']),
    ('EU family member birth', ['eu_family_member.date_of_birth']),
    ('exemption requires eu_family_member', ['eu_family_exemption', 'eu_family_member.surname']),
    (
        'exemption requires fields',
        ['eu_family_exemption', 'occupation.current_occupation', 'accommodation.name', 'expenses.paid_by'],
    ),
    ('non-exempt applications', ['occupation.current_occupation', 'expenses.paid_by', 'accommodation.name']),
    ('field_30 requires', ['expenses.sponsor.reference', 'accommodation.name']),
    ('field_31 requires', ['expenses.sponsor.reference', 'inviting_company.name']),
    ('departure_date must', ['journey.departure_date', 'journey.arrival_date']),
    ('valid_until must follow', ['passport.date_of_issue', 'passport.valid_until']),
    ('fingerprints_taken=false', ['previous_biometrics.fingerprints_taken', 'previous_biometrics.date']),
    ('residence=false', ['residence.lives_outside_country_of_nationality', 'residence.permit_type']),
    ('residence=true', ['residence.permit_type', 'residence.permit_number', 'residence.valid_until']),
    ('shared funding', ['expenses.paid_by', 'expenses.sponsor_means']),
    ('applicant_means must', ['expenses.applicant_means', 'expenses.paid_by']),
    ('sponsor funding requires', ['expenses.sponsor.reference', 'expenses.sponsor_means']),
    ('signature image_path', ['application.signature.enabled', 'application.signature.image_path']),
]


def friendly_message(error: dict) -> str:
    """Turn a Pydantic error into plain language; custom rule messages pass through."""
    kind, ctx = error['type'], error.get('ctx') or {}
    if kind in ('missing', 'string_too_short') or (kind == 'string_type' and error.get('input') is None):
        return 'This answer is required.'
    if kind == 'string_pattern_mismatch':
        if '[0-9]{4}' in str(ctx.get('pattern', '')):
            return 'Use the format DD-MM-YYYY, for example 23-04-1990.'
        return 'This answer is not in the expected format.'
    if kind == 'string_too_long':
        return f'This answer is too long (maximum {ctx.get("max_length")} characters).'
    if kind in ('bool_type', 'bool_parsing'):
        return 'Choose Yes or No.'
    if kind == 'too_short':
        return 'Choose or enter at least one item.'
    if kind in ('literal_error', 'enum'):
        return 'Choose one of the listed options.'
    if kind in ('dict_type', 'model_type', 'list_type'):
        return 'This section is incomplete. Answer its questions or mark it as not applicable.'
    message = error['msg'].removeprefix('Value error, ')
    return {
        'date must use DD-MM-YYYY': 'Use the format DD-MM-YYYY, for example 23-04-1990.',
        'date is not a valid calendar date': 'This date does not exist. Check the day and month.',
    }.get(message, message)


def validation_errors(data: dict) -> tuple[Applicant | None, list[dict]]:
    """Return field-linked errors without echoing applicant values."""
    try:
        # Keep pathological input from making text wrapping expensive.
        def text_bounds(v: Any) -> None:
            if isinstance(v, str) and len(v) > 4000:
                raise ValueError('An applicant value exceeds 4,000 characters')
            if isinstance(v, dict):
                for child in v.values():
                    text_bounds(child)
            if isinstance(v, list):
                for child in v:
                    text_bounds(child)

        text_bounds(data)
        return Applicant.model_validate(data), []
    except ValidationError as exc:
        fields = metadata()['fields']
        paths = [f['path'] for f in fields]
        errors = []
        for error in exc.errors():
            location = list(error['loc'])
            stay_index = (
                location[1]
                if len(location) > 1 and location[0] == 'accommodation' and isinstance(location[1], int)
                else None
            )
            path = '.'.join(str(p) for p in location if not isinstance(p, int))
            message = error['msg'].removeprefix('Value error, ')
            linked = next((v for phrase, v in ERROR_LINKS if phrase in message), [])
            message = friendly_message(error)
            if not linked:
                candidates = [p for p in paths if p == path or p.startswith(path + '.')]
                # Model-level other/detail rules mention the affected property.
                matching = [p for p in candidates if p.rsplit('.', 1)[-1] in message]
                linked = matching or (candidates[:1] if candidates else [path])
            if stay_index is not None and stay_index > 0:
                linked = [p.replace('accommodation.', f'accommodation.{stay_index}.', 1) for p in linked]
            errors.append({'path': linked[0] if linked else path, 'paths': linked, 'message': message})
        return None, errors
    except ValueError as exc:
        return None, [{'path': '', 'paths': [], 'message': str(exc)}]


class LocalServer(ThreadingHTTPServer):
    """Connections are accepted concurrently so an idle browser socket never blocks the app;
    request work runs under one lock, which also serializes all PyMuPDF operations."""

    daemon_threads = True
    # Browsers fetch every JS module in parallel; the default backlog of 5 resets some of them.
    request_queue_size = 64

    def __init__(self, address: tuple[str, int]):
        super().__init__(address, Handler)
        self.lock = threading.Lock()
        self.token = secrets.token_urlsafe(32)
        self.artifacts: OrderedDict[str, dict] = OrderedDict()
        self.origin = f'http://127.0.0.1:{self.server_port}'

    def purge(self) -> None:
        """Keep generated personal documents briefly and only in memory."""
        cutoff = time.monotonic() - 900
        for key in list(self.artifacts):
            if self.artifacts[key]['created'] < cutoff:
                del self.artifacts[key]
        while len(self.artifacts) > 8:
            self.artifacts.popitem(last=False)


class Handler(BaseHTTPRequestHandler):
    server: LocalServer

    def setup(self) -> None:
        super().setup()
        self.connection.settimeout(15)

    def log_message(self, format: str, *args: Any) -> None:
        """Do not persist requests, filenames, applicant data or artifact tokens."""

    def send_bytes(self, status: int, data: bytes, content_type: str, filename: str | None = None) -> None:
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('Cross-Origin-Resource-Policy', 'same-origin')
        self.send_header(
            'Content-Security-Policy',
            "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' blob: data:; connect-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'",
        )
        if filename:
            self.send_header('Content-Disposition', f'attachment; filename="{filename}"')
        self.end_headers()
        with contextlib.suppress(BrokenPipeError, ConnectionResetError):
            self.wfile.write(data)

    def reply(self, status: int, value: dict) -> None:
        self.send_bytes(status, json.dumps(value, ensure_ascii=False).encode(), 'application/json; charset=utf-8')

    def permitted(self, post: bool = False) -> bool:
        host = f'127.0.0.1:{self.server.server_port}'
        origin = self.headers.get('Origin')
        if (
            self.headers.get('Host') != host
            or (origin and origin != self.server.origin)
            or self.headers.get('Sec-Fetch-Site') == 'cross-site'
        ):
            self.reply(403, {'error': 'Only the local app origin is allowed'})
            return False
        if post and (
            origin != self.server.origin
            or not secrets.compare_digest(self.headers.get('X-App-Token', ''), self.server.token)
        ):
            self.reply(403, {'error': 'Reload the local app to refresh its session'})
            return False
        return True

    def do_GET(self) -> None:
        with self.server.lock:
            self.handle_get()

    def do_POST(self) -> None:
        with self.server.lock:
            self.handle_post()

    def handle_get(self) -> None:
        if not self.permitted():
            return
        route = urlsplit(self.path).path
        if route in ASSETS:
            filename, content_type = ASSETS[route]
            self.send_bytes(200, (Path(__file__).resolve().parent / 'static' / filename).read_bytes(), content_type)
        elif route == '/api/bootstrap':
            self.reply(200, {**metadata(), 'profiles': [], 'token': self.server.token})
        elif match := re.fullmatch(r'/api/artifacts/([A-Za-z0-9_-]+)/(pdf|page-[1-4]\.png)', route):
            self.server.purge()
            artifact = self.server.artifacts.get(match[1])
            if not artifact:
                self.reply(404, {'error': 'Preview expired. Generate it again.'})
                return
            if match[2] == 'pdf':
                self.send_bytes(200, artifact['pdf'], 'application/pdf', artifact['filename'])
            else:
                index = int(match[2][5]) - 1
                if index not in artifact['pages']:
                    with fitz.open(stream=artifact['pdf'], filetype='pdf') as doc:
                        artifact['pages'][index] = doc[index].get_pixmap(dpi=120, alpha=False).tobytes('png')
                self.send_bytes(200, artifact['pages'][index], 'image/png')
        else:
            self.reply(404, {'error': 'Not found'})

    def handle_post(self) -> None:
        if not self.permitted(post=True):
            return
        try:
            if self.headers.get('Transfer-Encoding'):
                raise ValueError('Chunked requests are not supported')
            size = int(self.headers.get('Content-Length', '0'))
            if not 0 < size <= MAX_BODY:
                self.reply(413, {'error': 'Request is empty or exceeds the 3 MB limit'})
                return
            if self.headers.get_content_type() != 'application/json':
                self.reply(415, {'error': 'Use application/json'})
                return
            body = parse_object(self.rfile.read(size).decode('utf-8'))
            route = urlsplit(self.path).path
            if route == '/api/parse':
                data = parse_object(body.get('text', ''))
                if isinstance(data.get('accommodation'), dict):
                    data['accommodation'] = [data['accommodation']]
                _, errors = validation_errors(data)
                self.reply(200, {'data': data, 'errors': errors})
                return
            if route not in ('/api/validate', '/api/generate'):
                self.reply(404, {'error': 'Not found'})
                return
            data = body.get('data')
            if not isinstance(data, dict):
                raise ValueError('Applicant data must be an object')
            applicant, errors = validation_errors(data)
            if errors:
                self.reply(422, {'errors': errors})
                return
            image = body.get('signature')
            signature = None
            if image is not None:
                if not isinstance(image, str):
                    raise ValueError('Signature must be a base64 image')
                signature = base64.b64decode(image, validate=True)
                if len(signature) > 1_500_000:
                    raise ValueError('Signature image must be smaller than 1.5 MB')
            assert applicant is not None
            if route == '/api/validate':
                prepare(applicant, Path('.'), signature_bytes=signature, allow_signature_path=False)
                self.reply(200, {'valid': True})
                return
            pdf = render_pdf_bytes(applicant, signature_bytes=signature)
            token = secrets.token_urlsafe(24)
            name = re.sub(r'[^A-Za-z0-9_-]+', '_', str(body.get('name', 'applicant')))[:70].strip('_-') or 'applicant'
            draft = (
                applicant.previous_biometrics.fingerprints_taken is None
                or body.get('draft', True) is not False
                or bool(re.search(r'FICTIONAL|DEMO-|\.example', json.dumps(data), re.I))
            )
            filename = f'{name}_schengen_application' + ('_draft' if draft else '') + '.pdf'
            revision = str(body.get('revision', ''))[:100]
            self.server.artifacts[token] = {
                'created': time.monotonic(),
                'pdf': pdf,
                'pages': {},
                'filename': filename,
                'revision': revision,
            }
            self.server.purge()
            prefix = '/api/artifacts/' + token
            self.reply(
                200,
                {
                    'pdf': prefix + '/pdf',
                    'pages': [prefix + f'/page-{n}.png' for n in range(1, 5)],
                    'filename': filename,
                    'revision': revision,
                    'draft': draft,
                },
            )
        except (ValueError, TypeError, UnicodeError, RecursionError) as exc:
            message = str(exc)
            path = message.split(':', 1)[0]
            known = {f['path'] for f in metadata()['fields']}
            if path not in known:
                path = next((p for p in known if p.startswith(path + '.')), '')
            self.reply(422, {'errors': [{'path': path, 'paths': [path] if path else [], 'message': message}]})
        except Exception:
            self.reply(500, {'error': 'Generation could not finish. Check the template and image, then try again.'})


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
