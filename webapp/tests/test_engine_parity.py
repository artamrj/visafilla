"""The in-browser engine must behave exactly like the Python engine.

Each case runs through webapp/static/engine (under Node) and through the Python reference
(script.core + webapp.validation); errors, field values, checkboxes, wrapped lines and font
sizes must be identical.
"""

from __future__ import annotations

import base64
import json
import shutil
import subprocess
from copy import deepcopy
from pathlib import Path

import pymupdf as fitz
import pytest

from script.core.paths import SPAIN_FORM_DIR
from script.core.renderer import prepare, values_and_checks
from script.core.schema import Applicant
from script.tests.scenarios import example, scenarios
from webapp import build, validation

NODE = shutil.which('node')
pytestmark = pytest.mark.skipif(NODE is None, reason='Node.js is needed to run the browser engine')
CLI = Path(__file__).with_name('engine_cli.mjs')


def run_js(cases: list[dict]) -> list[dict]:
    result = subprocess.run(
        [NODE, str(CLI)], input=json.dumps(cases), capture_output=True, text=True, check=True, timeout=120
    )
    return json.loads(result.stdout)


def run_python(case: dict) -> dict:
    if 'text' in case:
        try:
            validation.parse_object(case['text'])
            return {'parsed': True}
        except ValueError:
            return {'parsed': False}
    signature = base64.b64decode(case['signature']) if case.get('signature') else None
    errors = validation.check(case['data'], signature)
    if errors:
        return {'errors': errors}
    applicant = Applicant.model_validate(case['data'])
    values, checks = values_and_checks(applicant)
    _, placements, _, _ = prepare(applicant, Path('.'), signature_bytes=signature, allow_signature_path=False)
    return {
        'errors': [],
        'values': values,
        'checks': checks,
        'placements': [{'key': p.key, 'lines': p.lines, 'size': p.size} for p in placements],
    }


def compare(cases: list[dict]) -> None:
    js = run_js(cases)
    for case, actual in zip(cases, js, strict=True):
        expected = run_python(case)
        if 'text' in case:
            actual = {'parsed': actual['parsed']}
        assert actual == expected, json.dumps({'case': case, 'python': expected, 'browser': actual})[:3000]


def test_meta_json_is_current():
    assert not build.stale(), 'run python -m webapp.build'


def test_valid_scenarios_fill_identically():
    sample = json.loads((SPAIN_FORM_DIR / 'sample.json').read_text())
    compare([{'data': data} for data in [*scenarios().values(), sample]])


def leaves(value, path=()):
    if isinstance(value, dict):
        for key, child in value.items():
            yield from leaves(child, (*path, key))
    elif isinstance(value, list) and value and isinstance(value[0], dict):
        for i, child in enumerate(value):
            yield from leaves(child, (*path, i))
    else:
        yield path


def mutated(data, path, action, value=None):
    data = deepcopy(data)
    target = data
    for key in path[:-1]:
        target = target[key]
    if action == 'delete':
        del target[path[-1]]
    else:
        target[path[-1]] = value
    return data


def test_every_field_mutation_reports_the_same_errors():
    base = json.loads((SPAIN_FORM_DIR / 'sample.json').read_text())
    cases = []
    for path in leaves(base):
        for action, value in [('delete', None), ('set', None), ('set', '   '), ('set', 5), ('set', 'x'), ('set', True)]:
            cases.append({'data': mutated(base, path, action, value)})
    for section in ['personal', 'passport', 'journey', 'occupation', 'expenses', 'application', 'residence']:
        cases.append({'data': mutated(base, (section,), 'set', None)})
        cases.append({'data': mutated(base, (section,), 'set', [])})
        cases.append({'data': mutated(base, (section, 'unexpected'), 'set', 'value')})
    compare(cases)


def edge_cases() -> list[dict]:
    base = example()
    out = []

    def case(**changes):
        data = deepcopy(base)
        for dotted, value in changes.items():
            target = data
            *parents, last = dotted.split('__')
            for key in parents:
                target = target[key]
            target[last] = value
        out.append({'data': data})

    case(passport__valid_until='01-06-2027')
    case(passport__date_of_issue='01-01-2031')
    case(personal__date_of_birth='01-01-2015')
    case(personal__date_of_birth='31-02-1990')
    case(personal__date_of_birth='1990-02-01')
    case(personal__marital_status='other')
    case(personal__surname='EXAMPLE\u0007')
    case(personal__surname='محمدی')
    case(personal__surname='EXAMPLE ' * 40)
    case(personal__other_nationalities=['X', 'X'])
    case(journey__purposes=['tourism', 'tourism'])
    case(journey__purposes=['other'])
    case(journey__purposes=[])
    case(journey__main_destination=[])
    case(journey__departure_date='01-05-2027')
    case(journey__additional_information='VERY LONG NOTE ' * 30)
    case(contact__email='not-an-email')
    case(contact__home_address='LINE ONE\r\nLINE TWO, TEHRAN, IRAN')
    case(residence={'lives_outside_country_of_nationality': True})
    case(
        residence={
            'lives_outside_country_of_nationality': False,
            'permit_type': 'X',
            'permit_number': None,
            'valid_until': None,
        }
    )
    case(previous_biometrics={'fingerprints_taken': False, 'date': '01-01-2020', 'visa_sticker_number': None})
    case(previous_biometrics={'fingerprints_taken': None, 'date': '01-01-2020'})
    case(previous_biometrics={'fingerprints_taken': True, 'date': '01-01-2030'})
    case(accommodation=[])
    case(accommodation=None, inviting_company=None)
    case(eu_family_exemption=True)
    case(expenses__paid_by='sponsor')
    case(expenses__paid_by='shared', expenses__sponsor_means=['all_expenses_covered'])
    case(application__signature={'enabled': True, 'image_path': 'sig.png'})
    case(application__date='01-08-2027')
    case(unexpected_section={})
    for scenario in scenarios().values():
        stays = deepcopy(scenario.get('accommodation'))
        if isinstance(stays, dict):
            stays = [stays]
        if stays:
            first = dict(stays[0], city='Madrid', check_in='01-06-2027', check_out=None)
            second = dict(stays[0], city='Paris', check_in='10-06-2027', check_out='01-07-2027', email='bad')
            data = deepcopy(scenario)
            data['accommodation'] = [first, second]
            out.append({'data': data})
            data = deepcopy(scenario)
            data['accommodation'] = stays[0]  # legacy single object
            out.append({'data': data})
    return out


def test_edge_cases_report_the_same_errors():
    compare(edge_cases())


def test_signature_handling_matches():
    image = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 40, 12), False)
    image.clear_with(200)
    png = base64.b64encode(image.tobytes('png')).decode()
    base = example()
    signed = deepcopy(base)
    signed['application']['signature'] = {'enabled': True, 'image_path': 'sig.png'}
    compare(
        [
            {'data': signed, 'signature': png},
            {'data': signed, 'signature': base64.b64encode(b'not an image').decode()},
            {'data': base, 'signature': png},
        ]
    )


def test_strict_json_parsing_matches():
    compare(
        [
            {'text': '{"a": 1}'},
            {'text': '{"a": 1, "a": 2}'},
            {'text': '[]'},
            {'text': '{"n": NaN}'},
            {'text': '{"bad":'},
            {'text': '{"x": ' + '[' * 20 + ']' * 20 + '}'},
            {'text': json.dumps({'items': list(range(101))})},
            {'text': '{"text": "line\\nbreak", "esc": "\\u00e9"}'},
        ]
    )


def test_browser_font_asks_for_latin_spelling_outside_western_european_letters():
    """Known difference: the browser prints with standard Helvetica (Western European letters
    only), while PyMuPDF's font also covers letters such as Ş or ł. Passport machine-readable
    names use A-Z, so the browser asks for that spelling instead of printing a wrong glyph."""
    data = example()
    data['personal']['surname'] = 'ŞAHİN'
    [result] = run_js([{'data': data}])
    assert result['errors'] == [
        {
            'path': 'personal.surname',
            'paths': ['personal.surname'],
            'message': 'personal.surname: unsupported character U+015E; supply the passport Latin spelling',
        }
    ]
    data['personal']['surname'] = 'MÜLLER-GARCÍA'
    assert run_js([{'data': data}])[0]['errors'] == []


def test_generated_pdfs_look_identical():
    """Render every scenario from both engines and compare the pages pixel by pixel."""
    from script.core.renderer import render_pdf_bytes

    cases = [{'data': data, 'render': True} for data in scenarios().values()]
    for (name, data), result in zip(scenarios().items(), run_js(cases), strict=True):
        python_pdf = render_pdf_bytes(Applicant.model_validate(data))
        with fitz.open(stream=python_pdf) as expected, fitz.open(stream=base64.b64decode(result['pdf'])) as actual:
            assert len(expected) == len(actual) == 4
            for n in range(4):
                a = expected[n].get_pixmap(dpi=72, alpha=False).samples
                b = actual[n].get_pixmap(dpi=72, alpha=False).samples
                differing = sum(1 for i in range(0, len(a), 3) if abs(a[i] - b[i]) > 60)
                assert differing / (len(a) / 3) < 0.0005, f'{name} page {n + 1}'
