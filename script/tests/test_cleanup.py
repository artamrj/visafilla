"""Regression checks for shared parsing and successful template-check caching."""

import json
from dataclasses import replace
from pathlib import Path

import pytest

from script.core import renderer, utils
from script.core.schema import Applicant
from script.core.validator import load_applicant, parse_json_object
from webapp.server import parse_object

from .scenarios import example


@pytest.mark.parametrize(
    'text', ['{"a":1,"a":2}', '{"a":NaN}', '{"a":Infinity}', '{"a":-Infinity}', '[]', 'null', '1', '{bad']
)
def test_interfaces_share_json_errors(text, tmp_path):
    path = tmp_path / 'invalid.json'
    path.write_text(text)
    messages = []
    for action in (lambda: parse_json_object(text), lambda: parse_object(text), lambda: load_applicant(path)):
        with pytest.raises(ValueError) as error:
            action()
        messages.append(str(error.value))
    assert len(set(messages)) == 1


def test_cached_geometry_rechecks_coordinates_and_never_caches_failure(monkeypatch):
    applicant = Applicant.model_validate(example())
    monkeypatch.setattr(renderer, '_geometry_identity', None)
    original = renderer._check_geometry
    calls = []

    def checked(doc):
        calls.append(True)
        return original(doc)

    monkeypatch.setattr(renderer, '_check_geometry', checked)
    renderer.prepare(applicant, Path('.'))
    renderer.prepare(applicant, Path('.'))
    assert len(calls) == 1
    field = renderer.FIELD_MAP['personal.surname']
    monkeypatch.setitem(renderer.FIELD_MAP, 'personal.surname', replace(field, rect=(-1, -1, 10, 10)))
    for _ in range(2):
        with pytest.raises(ValueError, match='invalid coordinate'):
            renderer.prepare(applicant, Path('.'))
    assert len(calls) == 3
    monkeypatch.setitem(renderer.FIELD_MAP, 'personal.surname', field)
    renderer.prepare(applicant, Path('.'))
    assert len(calls) == 3


def test_template_content_and_manifest_invalidate_cache(monkeypatch, tmp_path):
    template = tmp_path / 'application.pdf'
    template.write_bytes(utils.TEMPLATE.read_bytes())
    folder = tmp_path / 'template'
    folder.mkdir()
    manifest_path = folder / 'manifest.json'
    original_manifest = (utils.TEMPLATE_DIR / 'manifest.json').read_bytes()
    manifest_path.write_bytes(original_manifest)
    monkeypatch.setattr(utils, 'TEMPLATE_DIR', folder)
    monkeypatch.setattr(utils, '_checked_template', None)
    utils.check_template(template)
    # The manifest is read on every invocation, even after a successful check.
    manifest = json.loads(original_manifest)
    manifest['pages'][0]['rotation'] = 90
    manifest_path.write_text(json.dumps(manifest))
    for _ in range(2):
        with pytest.raises(ValueError, match='geometry mismatch'):
            utils.check_template(template)
    manifest_path.write_bytes(original_manifest)
    template.write_bytes(template.read_bytes() + b'\nchanged')
    with pytest.raises(ValueError, match='SHA-256 mismatch'):
        utils.check_template(template)


def test_geometry_cache_tracks_template_and_manifest_content(monkeypatch, tmp_path):
    import hashlib

    folder = tmp_path / 'template'
    folder.mkdir()
    template = folder / 'application.pdf'
    template.write_bytes(utils.TEMPLATE.read_bytes())
    manifest_path = folder / 'manifest.json'
    manifest = json.loads((utils.TEMPLATE_DIR / 'manifest.json').read_bytes())
    manifest_path.write_text(json.dumps(manifest))
    monkeypatch.setattr(utils, 'TEMPLATE_DIR', folder)
    monkeypatch.setattr(utils, '_checked_template', None)
    monkeypatch.setattr(renderer, 'TEMPLATE', template)
    monkeypatch.setattr(renderer, 'check_template', lambda: utils.check_template(template))
    monkeypatch.setattr(renderer, '_geometry_identity', None)
    original = renderer._check_geometry
    calls = []

    def checked(doc):
        calls.append(True)
        return original(doc)

    monkeypatch.setattr(renderer, '_check_geometry', checked)
    applicant = Applicant.model_validate(example())
    renderer.prepare(applicant, Path('.'))
    renderer.prepare(applicant, Path('.'))
    assert len(calls) == 1
    manifest_path.write_text(json.dumps(manifest, indent=2))
    renderer.prepare(applicant, Path('.'))
    assert len(calls) == 2
    # A valid PDF with changed content and its updated manifest must be checked again.
    template.write_bytes(template.read_bytes() + b'\n')
    manifest['sha256'] = hashlib.sha256(template.read_bytes()).hexdigest()
    manifest_path.write_text(json.dumps(manifest))
    renderer.prepare(applicant, Path('.'))
    assert len(calls) == 3
