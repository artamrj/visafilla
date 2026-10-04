"""Fictional cases exercising every supported input and checkbox."""

import json
from copy import deepcopy
from pathlib import Path
from typing import get_args

from script.core.schema import Marital, PassportType, Purpose, Relationship


def example() -> dict:
    return json.loads((Path(__file__).resolve().parent / 'fixtures/applicant.json').read_text())


def scenarios() -> dict[str, dict]:
    base = example()
    cases = {'tourist': base}
    detailed = deepcopy(base)
    detailed['personal'].update(
        sex='female',
        marital_status='other',
        marital_status_other='FICTIONAL STATUS',
        nationality_at_birth='FICTIONAL NATIONALITY',
        other_nationalities=['FICTIONAL OTHER'],
    )
    detailed['passport'].update(type='other', type_other='FICTIONAL TRAVEL DOCUMENT')
    detailed['residence'] = {
        'lives_outside_country_of_nationality': True,
        'permit_type': 'RESIDENT',
        'permit_number': 'DEMO12345',
        'valid_until': '01-01-2029',
    }
    detailed['occupation'] = {
        'current_occupation': 'ENGINEER',
        'employer_or_school': {
            'name': 'EXAMPLE COMPANY',
            'address': '123 FICTIONAL ROAD, TEHRAN, IRAN',
            'phone': '+98 00 0000 0000',
        },
    }
    detailed['journey'].update(
        purposes=['business', 'visiting_family_or_friends', 'other'],
        purpose_other='FICTIONAL CONFERENCE',
        entries_requested='multiple',
    )
    detailed['previous_biometrics'] = {
        'fingerprints_taken': True,
        'date': '01-02-2024',
        'visa_sticker_number': 'EXAMPLE123',
    }
    detailed['final_destination_permit'] = {
        'issued_by': 'FICTIONAL AUTHORITY',
        'valid_from': '01-01-2027',
        'valid_until': '01-01-2028',
    }
    detailed['accommodation'].update(type='inviting_person', name='FICTIONAL HOST')
    detailed['inviting_company'] = {
        'name': 'EXAMPLE INVITING COMPANY',
        'address': '123 FICTIONAL ROAD, MADRID, SPAIN',
        'phone': '+34 000 000 000',
        'contact': {
            'surname': 'EXAMPLE',
            'given_names': 'CONTACT',
            'address': '123 FICTIONAL ROAD, MADRID, SPAIN',
            'email': 'Contact@company.example',
        },
    }
    detailed['expenses'] = {
        'paid_by': 'shared',
        'applicant_means': ['travellers_cheques', 'other'],
        'applicant_other': 'FICTIONAL SAVINGS',
        'sponsor_means': ['cash', 'accommodation_provided', 'prepaid_transport', 'other'],
        'sponsor_other': 'MEALS',
        'sponsor': {'reference': 'other', 'name': 'FICTIONAL SPONSOR'},
    }
    cases['detailed'] = detailed
    minor = deepcopy(base)
    minor['personal'].update(date_of_birth='01-01-2014', marital_status='single')
    minor['guardian'] = {
        'surname': 'EXAMPLE',
        'given_names': 'GUARDIAN',
        'nationality': 'IRANIAN',
        'address': '456 FICTIONAL ROAD, TEHRAN, IRAN',
        'phone': '+98 00 0000 0000',
        'email': 'Guardian@family.example',
    }
    minor['occupation'] = {
        'current_occupation': 'STUDENT',
        'employer_or_school': {'name': 'EXAMPLE SCHOOL', 'address': '789 FICTIONAL ROAD, TEHRAN, IRAN'},
    }
    minor['expenses'] = {
        'paid_by': 'sponsor',
        'sponsor_means': ['all_expenses_covered'],
        'sponsor': {'reference': 'field_30'},
    }
    cases['minor'] = minor
    eu = deepcopy(base)
    eu['eu_family_exemption'] = True
    eu['eu_family_member'] = {
        'surname': 'EXAMPLE',
        'given_names': 'EU RELATIVE',
        'date_of_birth': '01-01-1972',
        'nationality': 'SPANISH',
        'document_number': 'FICTIONAL-EU-ID',
        'relationship': 'spouse',
    }
    for k in ['occupation', 'accommodation', 'expenses']:
        eu[k] = None
    cases['eu_family'] = eu
    company = deepcopy(detailed)
    company['expenses'] = {
        'paid_by': 'sponsor',
        'sponsor_means': ['all_expenses_covered'],
        'sponsor': {'reference': 'field_31'},
    }
    cases['company_sponsor'] = company
    long = deepcopy(base)
    long['contact']['home_address'] = (
        'APARTMENT 12, FLOOR 3, FICTIONAL EXAMPLE RESIDENTIAL BUILDING, 123 IMAGINARY AVENUE, EXAMPLE DISTRICT, TEHRAN, IRAN'
    )
    long['accommodation']['address'] = (
        'SUITE 123, FICTIONAL EXAMPLE HOTEL COMPLEX, 456 IMAGINARY AVENUE, EXAMPLE DISTRICT, 28000 MADRID, SPAIN'
    )
    long['personal']['surname'] = 'EXAMPLE ' * 12
    cases['long_text'] = long
    for i, purpose in enumerate(get_args(Purpose)):
        item = deepcopy(eu)
        item['journey']['purposes'] = [purpose]
        item['journey']['purpose_other'] = 'FICTIONAL PURPOSE' if purpose == 'other' else None
        marital = get_args(Marital)[i % len(get_args(Marital))]
        item['personal'].update(
            marital_status=marital,
            marital_status_other='FICTIONAL STATUS' if marital == 'other' else None,
            sex='male' if i % 2 else 'female',
        )
        passport = get_args(PassportType)[i % len(get_args(PassportType))]
        item['passport'].update(type=passport, type_other='FICTIONAL DOCUMENT' if passport == 'other' else None)
        rel = get_args(Relationship)[i % len(get_args(Relationship))]
        item['eu_family_member'].update(
            relationship=rel, relationship_other='FICTIONAL RELATION' if rel == 'other' else None
        )
        item['journey']['entries_requested'] = ['single', 'double', 'multiple'][i % 3]
        cases[f'choices_{i + 1:02}'] = item
    return cases
