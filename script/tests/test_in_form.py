"""Blank biometric answers and multiple stays must survive the shared pipeline."""

from pathlib import Path

import pymupdf as fitz

from script.core.renderer import fill_pdf, values_and_checks
from script.core.schema import Applicant

from .scenarios import example


def test_unknown_fingerprints_preserve_previous_visa(tmp_path: Path):
    data = example()
    data['previous_biometrics'] = {
        'fingerprints_taken': None,
        'date': None,
        'visa_sticker_number': 'EXAMPLE123',
        'visa_issuing_country': 'AUSTRIA',
        'visa_entry_date': '15-03-2023',
    }
    applicant = Applicant.model_validate(data)
    values, checks = values_and_checks(applicant)
    assert not any(c.startswith('fingerprints.') for c in checks)
    assert values['previous_biometrics.visa_sticker_number'] == 'EXAMPLE123'
    assert values['journey.additional_information'] == 'TOURISM IN SPAIN - FICTIONAL EXAMPLE'
    assert 'PREVIOUS VISA' not in values['journey.additional_information']
    assert 'ENTRY 15-03-2023' not in values['journey.additional_information']
    assert Applicant.model_validate_json(applicant.model_dump_json()).previous_biometrics.fingerprints_taken is None
    target = tmp_path / 'blank.pdf'
    fill_pdf(applicant, target, tmp_path)
    with fitz.open(target) as pdf:
        assert len(pdf) == 4
        assert 'EXAMPLE123' in pdf[1].get_text()


def test_multiple_stays_fit_without_supplement(tmp_path: Path):
    data = example()
    data['contact']['home_address'] = (
        '2nd Floor, Unit 4, Building Example, No. 5 Example Dead End, Example 12, Example 4, Main Road, Sample Town, Sample Region, Example, 0000000000'
    )
    data['accommodation'].update(
        name='Madrid rental: Example flat, 3 beds/3 baths + lift - 8 guests\nBarcelona rental: Example 4-bedroom penthouse with large terrace\nParis rental: Example apartment - 3BR/10P - city centre',
        address='Madrid: Calle de Ejemplo Ficticio, 12 3 - Derecha, Madrid, Comunidad de Madrid 28000, Spain\nBarcelona: Carrer de l Exemple, 100, Barcelona, Catalunya 08000, Spain\nParis: 10 Rue Imaginaire, Paris, Ile-de-France 75000, France',
        phone='Madrid: +34 000 000 001\nBarcelona: +34 000 000 002\nParis: +33 0 00 00 00 03',
        booking_details='Madrid 01-06 to 04-06-2027: BOOKING001; Barcelona 04-06 to 09-06-2027: BOOKING002; Paris 09-06 to 15-06-2027: BOOKING003',
    )
    target = tmp_path / 'stays.pdf'
    fill_pdf(Applicant.model_validate(data), target, tmp_path)
    with fitz.open(target) as pdf:
        assert len(pdf) == 4
        text = ' '.join(' '.join(page.get_text() for page in pdf).split()).upper()
        for key in ['name', 'address', 'phone', 'booking_details']:
            assert ' '.join(data['accommodation'][key].split()).upper() in text
        assert ' '.join(data['contact']['home_address'].split()).upper() in text
        assert 'SUPPLEMENT' not in text


def test_accommodation_array_roundtrip_and_stay_dates(tmp_path: Path):
    from copy import deepcopy

    import pytest
    from pydantic import ValidationError

    data = example()
    first = dict(
        data['accommodation'],
        city='Madrid',
        check_in='01-06-2027',
        check_out='04-06-2027',
        confirmation_code='BOOKING001',
    )
    second = dict(
        first,
        city='Barcelona',
        name='SECOND EXAMPLE STAY',
        email=None,
        check_in='04-06-2027',
        check_out='15-06-2027',
        confirmation_code='BOOKING002',
    )
    data['accommodation'] = [first, second]
    applicant = Applicant.model_validate(data)
    exported = applicant.model_dump(mode='json')
    assert isinstance(exported['accommodation'], list) and len(exported['accommodation']) == 2
    target = tmp_path / 'array.pdf'
    fill_pdf(applicant, target, tmp_path)
    with fitz.open(target) as pdf:
        assert len(pdf) == 4
        text = ' '.join(page.get_text() for page in pdf)
        for value in ['MADRID: FICTIONAL EXAMPLE HOTEL', 'BARCELONA: SECOND EXAMPLE STAY']:
            assert value in text
    bad = deepcopy(data)
    bad['accommodation'][1]['check_out'] = '03-06-2027'
    with pytest.raises(ValidationError, match='accommodation dates'):
        Applicant.model_validate(bad)
    data['accommodation'] = first
    assert isinstance(Applicant.model_validate(data).model_dump()['accommodation'], list)


def test_accommodation_country_is_preserved_and_printed():
    data = example()
    data['accommodation'] = [
        dict(data['accommodation'], city='Madrid', country='Spain', address='123 Example Street, Madrid')
    ]
    applicant = Applicant.model_validate(data)
    assert applicant.model_dump()['accommodation'][0]['country'] == 'Spain'
    values, _ = values_and_checks(applicant)
    assert values['accommodation.address'].splitlines()[0].split(';')[0] == 'MADRID: 123 EXAMPLE STREET, MADRID, SPAIN'
    data['accommodation'][0]['address'] += ' , Spain'
    values, _ = values_and_checks(Applicant.model_validate(data))
    assert values['accommodation.address'].count('SPAIN') == 1


def test_accommodation_emails_stay_in_address_column(tmp_path: Path):
    data = example()
    data['accommodation'] = [
        dict(data['accommodation'], city=city, email=f'host.{city.lower()}@example.com')
        for city in ['Madrid', 'Barcelona', 'Paris']
    ]
    applicant = Applicant.model_validate(data)
    values, _ = values_and_checks(applicant)
    assert 'accommodation.email' not in values
    assert '@' not in values['accommodation.phone']
    assert values['accommodation.address'].splitlines() == [
        f"{stay['city'].upper()}: {stay['address'].upper()}; {stay['email']}" for stay in data['accommodation']
    ]
    target = tmp_path / 'email-columns.pdf'
    fill_pdf(applicant, target, tmp_path)
    with fitz.open(target) as pdf:
        words = pdf[1].get_text('words')
        for stay in data['accommodation']:
            assert stay['email'] in values['accommodation.address']
            email_words = [word for word in words if stay['email'] in word[4]]
            assert email_words
            assert all(51 <= word[0] < word[2] <= 294 and 735 <= word[1] < word[3] <= 776 for word in email_words)
