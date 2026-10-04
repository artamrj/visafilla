"""Local HTTP API security, validation, metadata and in-memory PDF tests."""

from __future__ import annotations

import base64
import json
import time
from http.client import HTTPConnection

import pymupdf as fitz

from script.core.utils import TEMPLATE
from script.tests.scenarios import example
from webapp.fields import LABELS
from webapp.server import MAX_BODY


def request(server, route, body=None, headers=None, method=None):
    conn = HTTPConnection('127.0.0.1', server.server_port, timeout=30)
    h = {'Origin': server.origin, 'X-App-Token': server.token, 'Content-Type': 'application/json'}
    if headers:
        h.update(headers)
    raw = json.dumps(body) if body is not None else None
    conn.request(method or ('POST' if body is not None else 'GET'), route, body=raw, headers=h)
    res = conn.getresponse()
    data = res.read()
    status = res.status
    response_headers = dict(res.getheaders())
    conn.close()
    if 'application/json' in response_headers.get('Content-Type', ''):
        data = json.loads(data)
    return status, data, response_headers


def test_bootstrap_metadata_and_sources(web_server):
    status, data, headers = request(web_server, '/api/bootstrap')
    assert status == 200
    assert data['profiles'] == []
    assert len(data['steps']) == 8 and len(data['fields']) == 89
    assert {f['path'] for f in data['fields']} == set(LABELS)
    assert all(any('\u0600' <= c <= '\u06ff' for c in f['hint_fa']) for f in data['fields'])
    assert all(
        f['kind'] in {'string', 'select', 'multi', 'boolean', 'date', 'list', 'textarea', 'file'}
        for f in data['fields']
    )
    assert headers['Cache-Control'] == 'no-store'


def test_local_origin_and_filesystem_guards(web_server):
    for headers in [{'Host': 'evil.example'}, {'Origin': 'https://evil.example'}, {'Sec-Fetch-Site': 'cross-site'}]:
        assert request(web_server, '/api/bootstrap', headers=headers)[0] == 403
    assert request(web_server, '/api/validate', {'data': example()}, headers={'X-App-Token': 'bad'})[0] == 403
    for route in [
        '/data/alpha.json',
        '/../data/alpha.json',
        '/%2e%2e/data/alpha.json',
        '/template/schengen_application.pdf',
        '/.gitignore',
    ]:
        assert request(web_server, route)[0] == 404
    assert (
        request(web_server, '/api/validate', {'data': example()}, headers={'Content-Length': str(MAX_BODY + 1)})[0]
        == 413
    )
    assert request(web_server, '/api/validate', {'data': example()}, headers={'Content-Type': 'text/plain'})[0] == 415


def test_sample_applicant_is_complete_and_valid(web_server):
    status, meta, _ = request(web_server, '/api/bootstrap')
    assert status == 200
    status, result, _ = request(web_server, '/api/validate', {'data': meta['sample']})
    assert status == 200, result


def test_validation_messages_are_plain_language(web_server):
    data = example()
    data['personal']['given_names'] = None
    data['personal']['date_of_birth'] = 'b'
    data['personal']['country_of_birth'] = '   '
    data['eu_family_exemption'] = None
    status, result, _ = request(web_server, '/api/validate', {'data': data})
    assert status == 422
    messages = {e['path']: e['message'] for e in result['errors']}
    assert messages['personal.given_names'] == 'This answer is required.'
    assert messages['personal.date_of_birth'] == 'Use the format DD-MM-YYYY, for example 23-04-1990.'
    assert messages['personal.country_of_birth'] == 'This answer is required.'
    assert messages['eu_family_exemption'] == 'Choose Yes or No.'
    assert not any('pattern' in m or 'String should' in m or 'Input should' in m for m in messages.values())
    data = example()
    data['personal']['date_of_birth'] = '31-02-1970'
    messages = [e['message'] for e in request(web_server, '/api/validate', {'data': data})[1]['errors']]
    assert 'This date does not exist. Check the day and month.' in messages


def test_json_editor_parse_and_structured_errors(web_server):
    status, data, _ = request(web_server, '/api/parse', {'text': '{"personal": {"surname": "DRAFT"}}'})
    assert status == 200 and data['data']['personal']['surname'] == 'DRAFT'
    assert any(e['path'] == 'passport.type' for e in data['errors'])
    for text in ['{"bad":', '{"a":1,"a":2}', '[]', '{"n":NaN}']:
        assert request(web_server, '/api/parse', {'text': text})[0] == 422
    data = example()
    data['previous_biometrics']['date'] = '01-01-2020'
    status, result, _ = request(web_server, '/api/validate', {'data': data})
    assert status == 422
    assert result['errors'][0]['path'] == 'previous_biometrics.fingerprints_taken'
    data = example()
    data['personal']['surname'] = 'A' * 5000
    assert request(web_server, '/api/validate', {'data': data})[0] == 422


def test_generate_preserves_source_and_has_four_pages(web_server):
    original = TEMPLATE.read_bytes()
    assert request(web_server, '/api/validate', {'data': example()})[0] == 200
    status, result, _ = request(
        web_server, '/api/generate', {'data': example(), 'name': 'charlie', 'revision': '42', 'draft': True}
    )
    assert status == 200 and result['revision'] == '42' and result['filename'].endswith('_draft.pdf')
    assert len(result['pages']) == 4
    status, pdf, headers = request(web_server, result['pdf'])
    assert status == 200 and headers['Content-Type'] == 'application/pdf'
    with fitz.open(stream=pdf, filetype='pdf') as doc, fitz.open(TEMPLATE) as source:
        assert len(doc) == 4
        for a, b in zip(source, doc, strict=False):
            assert a.rect == b.rect
            for xref in a.get_contents():
                assert source.xref_stream(xref) == doc.xref_stream(xref)
    assert request(web_server, result['pages'][0])[1].startswith(b'\x89PNG')
    assert TEMPLATE.read_bytes() == original
    for a in web_server.artifacts.values():
        a['created'] = time.monotonic() - 1000
    assert request(web_server, result['pdf'])[0] == 404


def test_web_signature_requires_upload_never_reads_path(web_server, tmp_path):
    data = example()
    data['application']['signature'] = {'enabled': True, 'image_path': '/etc/passwd'}
    status, result, _ = request(web_server, '/api/generate', {'data': data})
    assert status == 422 and result['errors'][0]['path'] == 'application.signature.image_path'
    assert 'reattach' in result['errors'][0]['message']
    with fitz.open() as doc:
        page = doc.new_page(width=100, height=30)
        page.insert_text((3, 20), 'TEST')
        image = page.get_pixmap().tobytes('png')
    status, result, _ = request(
        web_server, '/api/generate', {'data': data, 'signature': base64.b64encode(image).decode()}
    )
    assert status == 200
    data['application']['signature'] = {'enabled': False, 'image_path': None}
    assert request(web_server, '/api/validate', {'data': data, 'signature': base64.b64encode(image).decode()})[0] == 422


def test_blank_fingerprints_generate_draft_without_losing_visa(web_server):
    data = example()
    data['previous_biometrics'].update(
        fingerprints_taken=None,
        visa_sticker_number='EXAMPLE123',
        visa_issuing_country='AUSTRIA',
        visa_entry_date='15-03-2023',
    )
    data['accommodation']['email'] = (
        'Madrid: Madrid@hotel.example\nBarcelona: Barcelona@hotel.example\nParis: Paris@hotel.example'
    )
    status, result, _ = request(web_server, '/api/generate', {'data': data, 'name': 'pending', 'draft': False})
    assert status == 200 and result['draft'] is True
    _, pdf, _ = request(web_server, result['pdf'])
    with fitz.open(stream=pdf, filetype='pdf') as doc:
        assert len(doc) == 4
        text = ' '.join(page.get_text() for page in doc)
        for expected in ['EXAMPLE123', 'Madrid@hotel.example', 'Barcelona@hotel.example', 'Paris@hotel.example']:
            assert expected in text


def test_modules_use_explicit_allowlist(web_server):
    for module in ('app', 'helpers', 'state', 'storage', 'rules', 'render', 'api', 'actions'):
        status, body, headers = request(web_server, f'/{module}.js')
        assert status == 200 and body
        assert headers['Content-Type'].startswith('text/javascript')
    for route in ('/unknown.js', '/../state.js', '/%2e%2e/state.js', '/server.py', '/tests/test_browser.py'):
        assert request(web_server, route)[0] == 404


def test_preview_pages_are_lazy_and_cached(web_server, monkeypatch):
    original = fitz.Page.get_pixmap
    calls = []

    def render_page(page, *args, **kwargs):
        calls.append(page.number)
        return original(page, *args, **kwargs)

    monkeypatch.setattr(fitz.Page, 'get_pixmap', render_page)
    status, result, _ = request(web_server, '/api/generate', {'data': example()})
    assert status == 200 and calls == []
    token = result['pdf'].split('/')[-2]
    artifact = web_server.artifacts[token]
    assert artifact['pages'] == {}
    first = request(web_server, result['pages'][2])
    second = request(web_server, result['pages'][2])
    assert first[0] == second[0] == 200
    assert first[1] == second[1] and first[1].startswith(b'\x89PNG')
    assert calls == [2]
    assert set(artifact['pages']) == {2}
    assert request(web_server, result['pages'][3])[0] == 200
    assert calls == [2, 3]
    artifact['created'] = time.monotonic() - 1000
    assert request(web_server, result['pages'][2])[0] == 404
