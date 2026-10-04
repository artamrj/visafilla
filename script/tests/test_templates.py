"""Reusable blank applicant, template loader and root-level country asset checks."""

import json
from pathlib import Path

import pytest

from script.cli import main
from script.core.paths import SPAIN_FORM_DIR, TEMPLATE, TEMPLATE_DIR, WORKSPACE_ROOT
from script.core.templates import TemplateError, load_country_template
from script.core.utils import check_template
from webapp.fields import metadata


def test_spain_assets_are_separate_from_processing_code():
    assert SPAIN_FORM_DIR == WORKSPACE_ROOT / 'template/spain'
    assert TEMPLATE.parent == SPAIN_FORM_DIR
    assert not (WORKSPACE_ROOT / 'script/template').exists()
    for filename in ('schengen_application.pdf', 'manifest.json', 'checkboxes.json', 'layout_evidence.json'):
        assert (SPAIN_FORM_DIR / filename).is_file()
    check_template()


def test_spain_resolves_identically_to_shared_base():
    spain = load_country_template('spain')
    base = json.loads((TEMPLATE_DIR / 'base.template.json').read_text())
    assert spain == base
    assert 'extras' not in spain


def test_blank_json_covers_every_supported_field_without_applicant_values(tmp_path):
    data = load_country_template('spain')
    fields = {}

    def walk(value, prefix=''):
        if isinstance(value, dict):
            for key, child in value.items():
                walk(child, f'{prefix}.{key}'.strip('.'))
        elif isinstance(value, list) and value and isinstance(value[0], dict):
            assert len(value) == 1
            walk(value[0], prefix)
        else:
            fields[prefix] = value

    walk(data)
    assert set(fields) == {field['path'] for field in metadata()['fields']}
    assert fields.pop('application.signature.enabled') is False
    assert all(value is None or value == [] for value in fields.values())
    # A scaffold must never be published as a complete application.
    out = tmp_path / 'output'
    assert main([str(SPAIN_FORM_DIR / 'spain.template.json'), '--output-dir', str(out)]) == 1
    assert not list(out.glob('*.pdf'))


def _tree(tmp_path):
    """Build a temp template dir with a base and country template, return TEMPLATE_DIR."""
    base = {
        'personal': {'surname': None, 'given_names': None, 'national_id': None},
        'accommodation': [{'name': None, 'city': None}],
    }
    (tmp_path / 'base.template.json').write_text(json.dumps(base))
    return tmp_path


def _write_country(directory: Path, name: str, definition: dict) -> None:
    (directory / name).mkdir(parents=True, exist_ok=True)
    (directory / name / f'{name}.template.json').write_text(json.dumps(definition))


def test_loader_nested_overrides_and_array_replacement(monkeypatch, tmp_path):
    _tree(tmp_path)
    _write_country(
        tmp_path,
        'country',
        {
            'extends': '../base.template.json',
            'overrides': {'personal': {'surname': 'EXAMPLE'}, 'accommodation': [{'name': 'REPLACED'}]},
            'extras': {'national_scheme': 'X'},
        },
    )
    monkeypatch.setattr('script.core.templates.TEMPLATE_DIR', tmp_path)
    result = load_country_template('country')
    assert result['personal']['surname'] == 'EXAMPLE'
    assert result['personal']['given_names'] is None
    assert result['accommodation'] == [{'name': 'REPLACED'}]
    assert result['extras'] == {'national_scheme': 'X'}


def test_loader_preserves_explicit_null(monkeypatch, tmp_path):
    _tree(tmp_path)
    _write_country(
        tmp_path, 'country', {'extends': '../base.template.json', 'overrides': {'personal': {'national_id': None}}}
    )
    monkeypatch.setattr('script.core.templates.TEMPLATE_DIR', tmp_path)
    result = load_country_template('country')
    assert result['personal']['national_id'] is None


def test_loader_results_are_independent(monkeypatch, tmp_path):
    _tree(tmp_path)
    _write_country(
        tmp_path, 'country', {'extends': '../base.template.json', 'overrides': {'personal': {'surname': 'A'}}}
    )
    _write_country(tmp_path, 'other', {'extends': '../base.template.json', 'overrides': {'personal': {'surname': 'B'}}})
    monkeypatch.setattr('script.core.templates.TEMPLATE_DIR', tmp_path)
    first = load_country_template('country')
    second = load_country_template('other')
    assert first['personal']['surname'] == 'A'
    assert second['personal']['surname'] == 'B'
    assert first != second


def test_loader_rejects_malformed_definitions(monkeypatch, tmp_path):
    _tree(tmp_path)
    for bad in [{'extends': 42}, {'extends': ''}, {'overrides': []}, {'extras': 'x'}]:
        _write_country(tmp_path, 'country', bad)
        monkeypatch.setattr('script.core.templates.TEMPLATE_DIR', tmp_path)
        with pytest.raises(TemplateError):
            load_country_template('country')


def test_loader_rejects_circular_and_outside_references(monkeypatch, tmp_path):
    _tree(tmp_path)
    outside_dir = tmp_path.parent / 'outside_templates'
    outside_dir.mkdir(exist_ok=True)
    outside = outside_dir / 'outside.json'
    outside.write_text('{}')
    _write_country(tmp_path, 'country', {'extends': str(outside)})
    monkeypatch.setattr('script.core.templates.TEMPLATE_DIR', tmp_path)
    with pytest.raises(TemplateError, match='outside template directory'):
        load_country_template('country')


def test_loader_rejects_circular_reference(monkeypatch, tmp_path):
    _tree(tmp_path)
    _write_country(
        tmp_path, 'country', {'extends': '../base.template.json', 'overrides': {'personal': {'surname': 'A'}}}
    )
    # Point a base back at the country via a second level.
    (tmp_path / 'base.template.json').write_text(json.dumps({'extends': 'country/country.template.json'}))
    monkeypatch.setattr('script.core.templates.TEMPLATE_DIR', tmp_path)
    with pytest.raises(TemplateError, match='circular'):
        load_country_template('country')
