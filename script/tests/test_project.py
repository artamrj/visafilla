"""End-to-end, schema and pixel-preservation regressions, all offline."""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from pathlib import Path
from typing import get_args

import pymupdf as fitz
import pytest
from pydantic import ValidationError

from script.cli import main
from script.core.coordinates import CHECKBOX_MAP, FIELD_MAP, OFFICIAL_USE, SIGNATURE
from script.core.renderer import fill_pdf, fit_text, prepare, values_and_checks
from script.core.schema import (
    Applicant,
    ApplicantMeans,
    Marital,
    PassportType,
    Purpose,
    Relationship,
    Sex,
    SponsorMeans,
)
from script.core.utils import TEMPLATE, check_template
from script.core.validator import load_applicant

from .scenarios import example, scenarios


@pytest.fixture
def data() -> dict:
    return example()


def set_value(data: dict, path: str, value: object) -> None:
    keys = path.split('.')
    for key in keys[:-1]:
        data = data[key]
    data[keys[-1]] = value


@pytest.mark.parametrize(
    'path,value',
    [
        ('personal.surname', ''),
        ('personal.given_names', ' '),
        ('passport.number', ''),
        ('personal.date_of_birth', '1970-01-01'),
        ('personal.date_of_birth', '31-02-1970'),
        ('personal.date_of_birth', '1-01-1970'),
        ('personal.date_of_birth', '29-02-2023'),
        ('personal.sex', 'other'),
        ('personal.marital_status', 'engaged'),
        ('passport.type', 'regular'),
        ('journey.purposes', ['holiday']),
        ('journey.purposes', []),
        ('journey.purposes', ['tourism', 'tourism']),
        ('journey.entries_requested', 'three'),
        ('journey.main_destination', []),
        ('previous_biometrics.fingerprints_taken', 'false'),
        ('residence.lives_outside_country_of_nationality', 0),
        ('previous_biometrics.date', '01-01-2020'),
        ('previous_biometrics.visa_sticker_number', 'EXAMPLE'),
        ('residence.permit_number', 'EXAMPLE'),
        ('residence.lives_outside_country_of_nationality', True),
        ('journey.departure_date', '01-01-2027'),
        ('passport.valid_until', '01-01-2020'),
        ('personal.marital_status', 'other'),
        ('passport.type', 'other'),
        ('journey.purposes', ['other']),
        ('application.signature.enabled', True),
        ('application.signature.image_path', 'signature.png'),
        ('expenses.sponsor_means', ['cash']),
        ('expenses.applicant_means', ['accommodation_provided']),
        ('expenses.applicant_means', ['other']),
        ('eu_family_exemption', True),
        ('personal.surname', 'NAME\u200b'),
        ('personal.surname', 123),
        ('contact.email', 'invalid'),
    ],
)
def test_rejects_invalid(data: dict, path: str, value: object) -> None:
    set_value(data, path, value)
    with pytest.raises(ValidationError):
        Applicant.model_validate(data)


@pytest.mark.parametrize(
    'path', ['personal.surname', 'personal.given_names', 'passport.number', 'application.date', 'journey.arrival_date']
)
def test_required(data: dict, path: str) -> None:
    section, key = path.split('.')
    del data[section][key]
    with pytest.raises(ValidationError):
        Applicant.model_validate(data)


def test_extra_and_duplicate_json(data: dict, tmp_path: Path) -> None:
    data['personal']['unexpected'] = True
    with pytest.raises(ValidationError):
        Applicant.model_validate(data)
    path = tmp_path / 'bad.json'
    path.write_text('{"personal":{},"personal":{}}')
    with pytest.raises(ValueError, match='duplicate'):
        load_applicant(path)


def test_all_fictional_scenarios(tmp_path: Path) -> None:
    covered = set()
    text_covered = set()
    for _name, raw in scenarios().items():
        a = Applicant.model_validate(raw)
        prepare(a, tmp_path)
        values, checks = values_and_checks(a)
        covered.update(checks)
        text_covered.update(values)
    assert covered == set(CHECKBOX_MAP)
    assert text_covered == set(FIELD_MAP)


@pytest.mark.parametrize(
    'prefix,enum',
    [
        ('sex', Sex),
        ('marital', Marital),
        ('passport', PassportType),
        ('relationship', Relationship),
        ('purpose', Purpose),
        ('applicant', ApplicantMeans),
        ('sponsor', SponsorMeans),
    ],
)
def test_enum_mapping(prefix: str, enum: object) -> None:
    assert all(f'{prefix}.{v}' in CHECKBOX_MAP for v in get_args(enum))


def test_exemption_and_guardian(data: dict) -> None:
    minor = scenarios()['minor']
    del minor['guardian']
    with pytest.raises(ValidationError, match='guardian'):
        Applicant.model_validate(minor)
    adult = deepcopy(data)
    adult['guardian'] = scenarios()['minor']['guardian']
    with pytest.raises(ValidationError, match='guardian'):
        Applicant.model_validate(adult)
    eu = scenarios()['eu_family']
    eu['occupation'] = data['occupation']
    with pytest.raises(ValidationError, match='exemption'):
        Applicant.model_validate(eu)


def test_sponsor_reference(data: dict) -> None:
    data['expenses'] = {'paid_by': 'sponsor', 'sponsor_means': ['cash'], 'sponsor': {'reference': 'field_31'}}
    with pytest.raises(ValidationError, match='field_31'):
        Applicant.model_validate(data)
    data['expenses'] = {
        'paid_by': 'shared',
        'applicant_means': ['cash'],
        'sponsor_means': ['all_expenses_covered'],
        'sponsor': {'reference': 'field_30'},
    }
    with pytest.raises(ValidationError, match='shared'):
        Applicant.model_validate(data)


def test_text_fit_unicode_and_email(data: dict, tmp_path: Path) -> None:
    data['personal']['surname'] = 'EXAMPLE ' * 12
    a = Applicant.model_validate(data)
    font, placements, _, _ = prepare(a, tmp_path)
    assert next(p for p in placements if p.key == 'personal.surname').size < 9
    assert values_and_checks(a)[0]['contact.email'] == data['contact']['email']
    with pytest.raises(ValueError, match='cannot fit'):
        fit_text('personal.surname', 'LONG ' * 1000, FIELD_MAP['personal.surname'], font)
    for bad in ['اسم', 'NAME🙂', 'कुमार']:
        with pytest.raises(ValueError, match='unsupported|shaping'):
            fit_text('personal.surname', bad, FIELD_MAP['personal.surname'], font)
    fit_text('personal.surname', 'ÉLÈNE MÜLLER', FIELD_MAP['personal.surname'], font)


def mask_rect(samples: bytearray, width: int, height: int, rect: fitz.Rect, scale: float) -> None:
    r = (rect * fitz.Matrix(scale, scale)).irect
    # One pixel accounts for raster edge rounding, not arbitrary adjacent content.
    x0 = max(0, r.x0 - 1)
    x1 = min(width, r.x1 + 1)
    for y in range(max(0, r.y0 - 1), min(height, r.y1 + 1)):
        samples[y * width + x0 : y * width + x1] = b'\0' * (x1 - x0)


@pytest.mark.parametrize('name', ['tourist', 'detailed', 'minor', 'eu_family', 'long_text'])
def test_pdf_preservation(name: str, tmp_path: Path) -> None:
    a = Applicant.model_validate(scenarios()[name])
    target = tmp_path / 'filled.pdf'
    before = hashlib.sha256(TEMPLATE.read_bytes()).hexdigest()
    fill_pdf(a, target, tmp_path)
    assert hashlib.sha256(TEMPLATE.read_bytes()).hexdigest() == before
    values, checks = values_and_checks(a)
    allowed = [FIELD_MAP[k] for k in values] + [CHECKBOX_MAP[k] for k in checks]
    with fitz.open(TEMPLATE) as source, fitz.open(target) as filled:
        assert len(filled) == 4
        for n, (s, t) in enumerate(zip(source, filled, strict=False)):
            assert s.mediabox == t.mediabox and s.cropbox == t.cropbox and s.rotation == t.rotation
            # Original streams are preserved byte-for-byte in the output.
            for xref in s.get_contents():
                assert source.xref_stream(xref) == filled.xref_stream(xref)
            scale = 2
            sp = s.get_pixmap(matrix=fitz.Matrix(scale, scale), colorspace=fitz.csGRAY)
            tp = t.get_pixmap(matrix=fitz.Matrix(scale, scale), colorspace=fitz.csGRAY)
            left = bytearray(sp.samples)
            right = bytearray(tp.samples)
            for field in allowed:
                if field.page == n:
                    mask_rect(left, sp.width, sp.height, fitz.Rect(field.rect), scale)
                    mask_rect(right, tp.width, tp.height, fitz.Rect(field.rect), scale)
            assert left == right, f'page {n + 1} changed outside permitted overlays'
        for field in [OFFICIAL_USE, SIGNATURE]:
            kwargs = {'clip': fitz.Rect(field.rect), 'dpi': 300}
            assert source[field.page].get_pixmap(**kwargs).samples == filled[field.page].get_pixmap(**kwargs).samples


def test_source_guards(data: dict, tmp_path: Path) -> None:
    a = Applicant.model_validate(data)
    with pytest.raises(ValueError, match='template'):
        fill_pdf(a, TEMPLATE, tmp_path, overwrite=True)
    other = tmp_path / 'other.pdf'
    other.write_bytes(b'wrong')
    with pytest.raises(ValueError, match='SHA-256'):
        check_template(other)
    target = tmp_path / 'exists.pdf'
    target.write_bytes(b'keep')
    with pytest.raises(ValueError, match='exists'):
        fill_pdf(a, target, tmp_path)
    assert target.read_bytes() == b'keep'


def test_batch_validation_preview_and_collision(data: dict, tmp_path: Path) -> None:
    inputs = tmp_path / 'data'
    inputs.mkdir()
    out = tmp_path / 'out'
    for name in ['alpha', 'bravo', 'charlie']:
        (inputs / f'{name}.json').write_text(json.dumps(data))
    assert main([str(inputs), '--validate-only', '--output-dir', str(out)]) == 0
    assert not out.exists()
    assert main([str(inputs), '--preview', '--dpi', '72', '--output-dir', str(out)]) == 0
    assert len(list(out.glob('*.pdf'))) == 3
    assert len(list(out.glob('*_preview/*.png'))) == 12
    assert main([str(inputs / 'alpha.json'), '--output-dir', str(out)]) == 1
    (inputs / 'invalid.json').write_text('{}')
    assert main([str(inputs), '--overwrite', '--output-dir', str(out)]) == 1
    collision = tmp_path / 'collision'
    collision.mkdir()
    for name in ['a b', 'a_b']:
        (collision / f'{name}.json').write_text(json.dumps(data))
    assert main([str(collision), '--output-dir', str(tmp_path / 'collision-out')]) == 1
    assert not (tmp_path / 'collision-out').exists()


def test_calibration_and_render(tmp_path: Path) -> None:
    assert main(['--calibrate', '--dpi', '72', '--output-dir', str(tmp_path)]) == 0
    assert len(list((tmp_path / 'calibration').glob('*.png'))) == 4
    index = json.loads((tmp_path / 'calibration/field-index.json').read_text())
    assert len(index) == len(FIELD_MAP) + len(CHECKBOX_MAP) + 1
    assert main(['--render-pdf', str(TEMPLATE), '--dpi', '72', '--output-dir', str(tmp_path)]) == 0
    assert len(list((tmp_path / 'schengen_application_render').glob('*.png'))) == 4


def test_signature_enabled(data: dict, tmp_path: Path) -> None:
    with fitz.open() as doc:
        p = doc.new_page(width=100, height=30)
        p.insert_text((2, 20), 'FICTIONAL')
        p.get_pixmap().save(tmp_path / 'signature.png')
    data['application']['signature'] = {'enabled': True, 'image_path': 'signature.png'}
    target = tmp_path / 'signed.pdf'
    fill_pdf(Applicant.model_validate(data), target, tmp_path)
    with fitz.open(target) as result, fitz.open(TEMPLATE) as original:
        assert (
            result[3].get_pixmap(clip=fitz.Rect(SIGNATURE.rect)).samples
            != original[3].get_pixmap(clip=fitz.Rect(SIGNATURE.rect)).samples
        )


def test_multiline_and_embedded_unicode(data: dict, tmp_path: Path) -> None:
    data['personal']['surname'] = 'ÉLÈNE MÜLLER'
    data['contact']['home_address'] = '123 FICTIONAL STREET\nTEHRAN, IRAN'
    a = Applicant.model_validate(data)
    target = tmp_path / 'unicode.pdf'
    fill_pdf(a, target, tmp_path)
    with fitz.open(target) as result:
        assert 'ÉLÈNE MÜLLER' in result[0].get_text()
        assert '123 FICTIONAL STREET\nTEHRAN, IRAN' in result[1].get_text()
    # Exercise explicit local font embedding instead of relying on fallback.
    font_path = tmp_path / 'local-font.cff'
    font_path.write_bytes(fitz.Font('helv').buffer)
    prepare(a, tmp_path, font_path)
    font = fitz.Font('helv')
    for key in ['occupation.employer_or_school', 'journey.additional_information']:
        placement = fit_text(key, 'FICTIONAL FIRST LINE\nFICTIONAL SECOND LINE', FIELD_MAP[key], font)
        assert len(placement.lines) == 2


def test_changed_coordinates_cannot_cover_labels_or_official_area(
    data: dict, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from script.core.coordinates import Field

    a = Applicant.model_validate(data)
    monkeypatch.setitem(FIELD_MAP, 'personal.surname', Field(0, (51, 190, 440, 210)))
    with pytest.raises(ValueError, match='original label'):
        prepare(a, tmp_path)
    monkeypatch.setitem(FIELD_MAP, 'personal.surname', Field(0, (449, 202, 500, 220)))
    with pytest.raises(ValueError, match='official-use'):
        prepare(a, tmp_path)


def test_validation_failures_do_not_publish_outputs(data: dict, tmp_path: Path) -> None:
    data['personal']['surname'] = 'EXAMPLE ' * 1000
    path = tmp_path / 'oversize.json'
    path.write_text(json.dumps(data))
    out = tmp_path / 'out'
    assert main([str(path), '--output-dir', str(out)]) == 1
    assert not out.exists()
    path.write_text('{broken JSON')
    assert main([str(path), '--validate-only']) == 1
    with pytest.raises(ValueError, match='line 1'):
        load_applicant(path)
