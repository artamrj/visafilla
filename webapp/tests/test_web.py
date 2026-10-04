"""Local static server security, published files and the reference validation messages."""

from __future__ import annotations

import hashlib
import json
from http.client import HTTPConnection
from pathlib import Path

from script.core.paths import SPAIN_FORM_DIR
from script.core.utils import TEMPLATE
from script.tests.scenarios import example
from webapp import validation
from webapp.build import STATIC
from webapp.fields import LABELS
from webapp.server import SECURITY_HEADERS


def request(server, route, headers=None, method='GET'):
    conn = HTTPConnection('127.0.0.1', server.server_port, timeout=30)
    conn.request(method, route, headers={'Origin': server.origin, **(headers or {})})
    res = conn.getresponse()
    data = res.read()
    response_headers = dict(res.getheaders())
    conn.close()
    if 'application/json' in response_headers.get('Content-Type', ''):
        data = json.loads(data)
    return res.status, data, response_headers


def test_meta_json_describes_the_whole_form(web_server):
    status, meta, headers = request(web_server, '/meta.json')
    assert status == 200
    assert len(meta['steps']) == 8 and len(meta['fields']) == 89
    assert {f['path'] for f in meta['fields']} == set(LABELS)
    assert all(any('؀' <= c <= 'ۿ' for c in f['hint_fa']) for f in meta['fields'])
    assert set(meta['layout']) == {'template', 'fields', 'checkboxes', 'signature'}
    assert headers['Cache-Control'] == 'no-store'
    # The committed copy served by the hosted site has the same content.
    assert json.loads((STATIC / 'meta.json').read_text()) == meta


def test_every_response_carries_the_security_headers(web_server):
    for route in ['/', '/meta.json', '/app.js', '/engine/index.js', '/vendor/pdf-lib.esm.min.js', '/nope']:
        _, _, headers = request(web_server, route)
        for name, value in SECURITY_HEADERS.items():
            assert headers[name] == value, (route, name)
    assert "connect-src 'self'" in SECURITY_HEADERS['Content-Security-Policy']


def test_hosted_headers_match_the_local_server():
    rules = (STATIC / '_headers').read_text()
    for name, value in SECURITY_HEADERS.items():
        assert f'{name}: {value}' in rules, name


def test_official_form_is_served_unchanged(web_server):
    status, pdf, headers = request(web_server, '/form/spain.pdf')
    assert status == 200 and headers['Content-Type'] == 'application/pdf'
    assert pdf == TEMPLATE.read_bytes() == (STATIC / 'form/spain.pdf').read_bytes()
    manifest = json.loads((SPAIN_FORM_DIR / 'manifest.json').read_text())
    assert hashlib.sha256(pdf).hexdigest() == manifest['sha256']


def test_local_origin_and_filesystem_guards(web_server):
    for headers in [{'Host': 'evil.example'}, {'Origin': 'https://evil.example'}, {'Sec-Fetch-Site': 'cross-site'}]:
        assert request(web_server, '/meta.json', headers=headers)[0] == 403
    for route in [
        '/../webapp/server.py',
        '/%2e%2e/script/core/schema.py',
        '/../template/spain/manifest.json',
        '/_headers',
        '/.gitignore',
        '/vendor/../../server.py',
        '/missing.js',
    ]:
        assert request(web_server, route)[0] == 404, route
    assert request(web_server, '/meta.json', method='POST')[0] == 405


def test_static_files_have_correct_types(web_server):
    for route, kind in [
        ('/', 'text/html'),
        ('/app.css', 'text/css'),
        ('/engine/schema.js', 'text/javascript'),
        ('/vendor/pdf.worker.min.mjs', 'text/javascript'),
    ]:
        status, _, headers = request(web_server, route)
        assert status == 200 and headers['Content-Type'].startswith(kind), route


def test_sample_applicant_is_complete_and_valid():
    sample = json.loads((SPAIN_FORM_DIR / 'sample.json').read_text())
    assert validation.check(sample) == []


def test_validation_messages_are_plain_language():
    data = example()
    data['personal']['given_names'] = None
    data['personal']['date_of_birth'] = 'b'
    data['personal']['country_of_birth'] = '   '
    data['eu_family_exemption'] = None
    messages = {e['path']: e['message'] for e in validation.check(data)}
    assert messages['personal.given_names'] == 'This answer is required.'
    assert messages['personal.date_of_birth'] == 'Use the format DD-MM-YYYY, for example 23-04-1990.'
    assert messages['personal.country_of_birth'] == 'This answer is required.'
    assert messages['eu_family_exemption'] == 'Choose Yes or No.'
    assert not any('pattern' in m or 'String should' in m or 'Input should' in m for m in messages.values())
    data = example()
    data['personal']['date_of_birth'] = '31-02-1970'
    assert 'This date does not exist. Check the day and month.' in [e['message'] for e in validation.check(data)]


def test_reference_errors_link_to_form_fields():
    data = example()
    data['previous_biometrics']['date'] = '01-01-2020'
    assert validation.check(data)[0]['path'] == 'previous_biometrics.fingerprints_taken'
    data = example()
    data['personal']['surname'] = 'A' * 5000
    assert validation.check(data) == [
        {'path': '', 'paths': [], 'message': 'An applicant value exceeds 4,000 characters'}
    ]


def test_no_applicant_endpoints_remain():
    source = Path(__file__).resolve().parents[1].joinpath('server.py').read_text()
    assert '/api/' not in source and 'do_POST' in source
