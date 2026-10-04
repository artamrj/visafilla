"""Complete form metadata for the browser UI; Persian guidance comes from guidance_fa."""

from __future__ import annotations

import json
from functools import lru_cache
from typing import Any

from script.core.paths import SPAIN_FORM_DIR, TEMPLATE_DIR
from script.core.schema import Applicant
from webapp.guidance_fa import FIELD_HINTS, GROUP_HINTS, STEP_GUIDES

# The 29 Schengen states as ISO 3166-1 alpha-2 code and English name. A country becomes
# selectable in the browser as soon as template/<name>/ exists.
SCHENGEN_COUNTRIES = [
    ('AT', 'Austria'),
    ('BE', 'Belgium'),
    ('BG', 'Bulgaria'),
    ('HR', 'Croatia'),
    ('CZ', 'Czechia'),
    ('DK', 'Denmark'),
    ('EE', 'Estonia'),
    ('FI', 'Finland'),
    ('FR', 'France'),
    ('DE', 'Germany'),
    ('GR', 'Greece'),
    ('HU', 'Hungary'),
    ('IS', 'Iceland'),
    ('IT', 'Italy'),
    ('LV', 'Latvia'),
    ('LI', 'Liechtenstein'),
    ('LT', 'Lithuania'),
    ('LU', 'Luxembourg'),
    ('MT', 'Malta'),
    ('NL', 'Netherlands'),
    ('NO', 'Norway'),
    ('PL', 'Poland'),
    ('PT', 'Portugal'),
    ('RO', 'Romania'),
    ('SK', 'Slovakia'),
    ('SI', 'Slovenia'),
    ('ES', 'Spain'),
    ('SE', 'Sweden'),
    ('CH', 'Switzerland'),
]


def countries() -> list[dict[str, Any]]:
    return [
        {'code': code, 'name': name, 'available': (TEMPLATE_DIR / name.lower()).is_dir()}
        for code, name in SCHENGEN_COUNTRIES
    ]


STEPS = [
    ('Personal details', 'Start with the passport'),
    ('Passport', 'Your travel document'),
    ('Contact & residence', 'Where you live'),
    ('Family & occupation', 'Your circumstances'),
    ('Travel', 'Map out the journey'),
    ('Biometrics & permits', 'Previous records'),
    ('Stay & expenses', 'Accommodation and funding'),
    ('Review & generate', 'One final check'),
]

# Every leaf in the runtime schema has an English label; Persian guidance lives in guidance_fa.
LABELS: dict[str, str] = {
    'personal.surname': 'Surname',
    'personal.surname_at_birth': 'Surname at birth / former surname',
    'personal.given_names': 'Given names',
    'personal.date_of_birth': 'Date of birth',
    'personal.place_of_birth': 'Place of birth',
    'personal.country_of_birth': 'Country of birth',
    'personal.current_nationality': 'Current nationality',
    'personal.nationality_at_birth': 'Nationality at birth',
    'personal.other_nationalities': 'Other nationalities',
    'personal.sex': 'Sex',
    'personal.marital_status': 'Marital status',
    'personal.marital_status_other': 'Other marital status — specify',
    'personal.national_id': 'National identity number',
    'passport.type': 'Travel document type',
    'passport.type_other': 'Other document — specify',
    'passport.number': 'Passport / document number',
    'passport.date_of_issue': 'Date of issue',
    'passport.valid_until': 'Valid until',
    'passport.issued_by': 'Issued by — country',
    'contact.home_address': 'Home address',
    'contact.email': 'Email address',
    'contact.phone': 'Telephone number',
    'residence.lives_outside_country_of_nationality': 'Do you live outside your country of nationality?',
    'residence.permit_type': 'Residence permit type',
    'residence.permit_number': 'Residence permit number',
    'residence.valid_until': 'Residence permit expiry',
    'occupation.current_occupation': 'Current occupation',
    'occupation.employer_or_school.name': 'Employer / school name',
    'occupation.employer_or_school.address': 'Employer / school address',
    'occupation.employer_or_school.phone': 'Employer / school telephone',
    'journey.purposes': 'Purpose of travel',
    'journey.purpose_other': 'Other travel purpose — specify',
    'journey.additional_information': 'Additional travel information',
    'journey.main_destination': 'Destination countries',
    'journey.first_entry_country': 'Country of first entry',
    'journey.entries_requested': 'Entries requested',
    'journey.arrival_date': 'Arrival date',
    'journey.departure_date': 'Departure date',
    'previous_biometrics.fingerprints_taken': 'Were Schengen fingerprints collected before?',
    'previous_biometrics.visa_issuing_country': 'Previous visa issuing country',
    'previous_biometrics.visa_entry_date': 'Previous visa entry date',
    'accommodation.booking_details': 'Booking dates and confirmation codes',
    'previous_biometrics.date': 'Fingerprint collection date, if known',
    'previous_biometrics.visa_sticker_number': 'Visa sticker number, if known',
    'accommodation.country': 'Country',
    'accommodation.city': 'City',
    'accommodation.check_in': 'Check-in date',
    'accommodation.check_out': 'Check-out date',
    'accommodation.confirmation_code': 'Booking confirmation code',
    'accommodation.type': 'Accommodation type',
    'accommodation.name': 'Host / accommodation name',
    'accommodation.address': 'Accommodation address',
    'accommodation.email': 'Accommodation contact email',
    'accommodation.phone': 'Accommodation telephone',
    'expenses.paid_by': 'Who pays for the trip?',
    'expenses.applicant_means': 'Applicant’s means of payment',
    'expenses.sponsor_means': 'Sponsor’s means of support',
    'expenses.applicant_other': 'Applicant — other means',
    'expenses.sponsor_other': 'Sponsor — other means',
    'expenses.sponsor.reference': 'Sponsor identification',
    'expenses.sponsor.name': 'Other sponsor’s name',
    'application.place': 'Place of application / signing',
    'application.date': 'Application / signing date',
    'application.signature.enabled': 'Insert a signature image?',
    'application.signature.image_path': 'Signature image',
    'guardian.surname': 'Guardian’s surname',
    'guardian.given_names': 'Guardian’s given names',
    'guardian.address': 'Guardian’s address, if different',
    'guardian.phone': 'Guardian’s telephone',
    'guardian.email': 'Guardian’s email',
    'guardian.nationality': 'Guardian’s nationality',
    'eu_family_member.surname': 'EU / EEA / Swiss relative’s surname',
    'eu_family_member.given_names': 'Relative’s given names',
    'eu_family_member.date_of_birth': 'Relative’s date of birth',
    'eu_family_member.nationality': 'Relative’s nationality',
    'eu_family_member.document_number': 'Relative’s passport / ID number',
    'eu_family_member.relationship': 'Relationship to that relative',
    'eu_family_member.relationship_other': 'Other relationship — specify',
    'eu_family_exemption': 'Use the EU-family exemption?',
    'inviting_company.name': 'Inviting company / organisation',
    'inviting_company.address': 'Inviting company address',
    'inviting_company.contact.surname': 'Company contact’s surname',
    'inviting_company.contact.given_names': 'Company contact’s given names',
    'inviting_company.contact.address': 'Company contact’s address',
    'inviting_company.contact.email': 'Company contact’s email',
    'inviting_company.phone': 'Inviting company telephone',
    'final_destination_permit.issued_by': 'Final-destination permit — issued by',
    'final_destination_permit.valid_from': 'Entry permit valid from',
    'final_destination_permit.valid_until': 'Entry permit valid until',
}

GROUPS = [
    {'path': 'personal', 'step': 0, 'title': 'As written in your passport', 'number': '01–11'},
    {'path': 'passport', 'step': 1, 'title': 'Travel document', 'number': '12–16'},
    {'path': 'contact', 'step': 2, 'title': 'Your contact details', 'number': '19'},
    {'path': 'residence', 'step': 2, 'title': 'Country of residence', 'number': '20'},
    {'path': 'eu_family_exemption', 'step': 3, 'title': 'Family circumstances', 'number': '17–18'},
    {
        'path': 'guardian',
        'step': 3,
        'title': 'Parental authority / legal guardian',
        'number': '10',
        'optional': True,
        'question': 'Does this applicant need a guardian section?',
    },
    {
        'path': 'eu_family_member',
        'step': 3,
        'title': 'EU / EEA / Swiss family member',
        'number': '17–18',
        'optional': True,
        'question': 'Do EU / EEA / Swiss family-member details apply?',
    },
    {'path': 'occupation', 'step': 3, 'title': 'Work or study', 'number': '21'},
    {
        'path': 'occupation.employer_or_school',
        'step': 3,
        'title': 'Employer or educational establishment',
        'number': '22',
        'optional': True,
        'question': 'Is there an employer, school or university to list?',
    },
    {'path': 'journey', 'step': 4, 'title': 'The trip you are applying for', 'number': '23–27'},
    {'path': 'previous_biometrics', 'step': 5, 'title': 'Previous Schengen fingerprints', 'number': '28'},
    {
        'path': 'final_destination_permit',
        'step': 5,
        'title': 'Final-destination entry permit',
        'number': '29',
        'optional': True,
        'question': 'Does a final-destination entry permit apply?',
    },
    {
        'path': 'accommodation',
        'step': 6,
        'title': 'Where you will stay',
        'number': '30',
        'optional': True,
        'question': 'List accommodation or an inviting person?',
    },
    {
        'path': 'inviting_company',
        'step': 6,
        'title': 'Inviting company',
        'number': '31',
        'optional': True,
        'question': 'Is a company or organisation inviting you?',
    },
    {'path': 'expenses', 'step': 6, 'title': 'Travel and living costs', 'number': '32'},
    {'path': 'application', 'step': 7, 'title': 'Place, date & signature', 'number': 'PAGE 4'},
]


# Browser presentation and clearing rules; model validation remains authoritative.
OTHER_FIELDS = {
    'personal.marital_status_other': ('personal.marital_status', 'other'),
    'passport.type_other': ('passport.type', 'other'),
    'journey.purpose_other': ('journey.purposes', 'other'),
    'eu_family_member.relationship_other': ('eu_family_member.relationship', 'other'),
    'expenses.applicant_other': ('expenses.applicant_means', 'other'),
    'expenses.sponsor_other': ('expenses.sponsor_means', 'other'),
    'expenses.sponsor.name': ('expenses.sponsor.reference', 'other'),
}
RESIDENCE_DETAILS = ['residence.permit_type', 'residence.permit_number', 'residence.valid_until']
EXEMPT_GROUPS = ['occupation', 'occupation.employer_or_school', 'accommodation', 'inviting_company', 'expenses']
CONDITIONAL_REQUIRED = (
    RESIDENCE_DETAILS
    + list(OTHER_FIELDS)
    + [
        'expenses.applicant_means',
        'expenses.sponsor_means',
        'application.signature.image_path',
        'eu_family_exemption',
    ]
)


def browser_rules(paths: list[str]) -> dict[str, Any]:
    visible = {path: [{'path': source, 'equals': value}] for path, (source, value) in OTHER_FIELDS.items()}
    for path in paths:
        conditions = visible.setdefault(path, [])
        if path.startswith('residence.') and path != 'residence.lives_outside_country_of_nationality':
            conditions.append({'path': 'residence.lives_outside_country_of_nationality', 'equals': True})
        if path.startswith('expenses.applicant_'):
            conditions.append({'path': 'expenses.paid_by', 'oneOf': ['applicant', 'shared']})
        if path.startswith('expenses.sponsor'):
            conditions.append({'path': 'expenses.paid_by', 'oneOf': ['sponsor', 'shared']})
    visible['previous_biometrics.date'] = [{'path': 'previous_biometrics.fingerprints_taken', 'equals': True}]
    visible['application.signature.image_path'] = [{'path': 'application.signature.enabled', 'equals': True}]
    return {
        'visible': {path: conditions for path, conditions in visible.items() if conditions},
        'required': CONDITIONAL_REQUIRED,
        'unavailable': {
            **{path: [{'path': 'eu_family_exemption', 'equals': True}] for path in EXEMPT_GROUPS},
            'guardian': [{'ageAtLeast': 18}],
        },
        'clear': [
            {
                'when': {'path': 'eu_family_exemption', 'equals': True},
                'paths': [path for path in EXEMPT_GROUPS if path != 'occupation.employer_or_school'],
            },
            {
                'when': {'path': 'residence.lives_outside_country_of_nationality', 'not': True},
                'paths': RESIDENCE_DETAILS,
            },
            {
                'when': {'path': 'previous_biometrics.fingerprints_taken', 'equals': False},
                'paths': ['previous_biometrics.date', 'previous_biometrics.visa_sticker_number'],
            },
            {'when': {'ageAtLeast': 18}, 'paths': ['guardian']},
            {'when': {'path': 'expenses.paid_by', 'notOneOf': ['sponsor', 'shared']}, 'paths': ['expenses.sponsor']},
        ],
    }


@lru_cache(maxsize=1)
def metadata() -> dict[str, Any]:
    """Derive controls from Pydantic; fail loudly if guidance ever falls behind."""
    schema = Applicant.model_json_schema()
    fields: list[dict[str, Any]] = []

    def walk(node: dict, path: str = '', required: bool = True) -> None:
        nullable = any(n.get('type') == 'null' for n in node.get('anyOf', []))
        if 'anyOf' in node:
            node = next(n for n in node['anyOf'] if n.get('type') != 'null')
        if path == 'accommodation' and node.get('type') == 'array':
            walk(node['items'], path, required)
            return
        if '$ref' in node:
            node = schema['$defs'][node['$ref'].split('/')[-1]]
        if 'properties' in node:
            for key, value in node['properties'].items():
                walk(value, f'{path}.{key}'.strip('.'), key in node.get('required', []))
        else:
            label, hint = LABELS[path], FIELD_HINTS[path]
            group = max(
                (g for g in GROUPS if path == g['path'] or path.startswith(g['path'] + '.')),
                key=lambda g: len(g['path']),
            )
            kind = node.get('type', 'string')
            options = node.get('enum') or node.get('items', {}).get('enum')
            if options:
                kind = 'multi' if kind == 'array' else 'select'
            elif kind == 'array':
                kind = 'list'
            elif path == 'application.signature.image_path':
                kind = 'file'
            elif 'pattern' in node:
                kind = 'date'
            elif path.endswith(('address', 'additional_information', 'booking_details')) or path in (
                'accommodation.name',
                'accommodation.phone',
                'accommodation.email',
            ):
                kind = 'textarea'
            fields.append(
                {
                    'path': path,
                    'label': label,
                    'hint_fa': hint,
                    'group': group['path'],
                    'step': group['step'],
                    'required': required and not nullable,
                    'nullable': nullable,
                    'kind': kind,
                    'options': options or [],
                }
            )

    walk(schema)
    assert {f['path'] for f in fields} == set(LABELS) == set(FIELD_HINTS)
    assert set(GROUP_HINTS) == {g['path'] for g in GROUPS if g.get('optional')}
    assert len(STEP_GUIDES) == len(STEPS)
    return {
        'steps': [{'title': t, 'subtitle': s, 'hint_fa': h} for (t, s), h in zip(STEPS, STEP_GUIDES, strict=True)],
        'groups': [{**g, 'hint_fa': GROUP_HINTS[g['path']]} if g.get('optional') else g for g in GROUPS],
        'fields': fields,
        'schema': schema,
        'rules': browser_rules([f['path'] for f in fields]),
        'countries': countries(),
        # A complete, fictional applicant people can explore before entering their own.
        'sample': json.loads((SPAIN_FORM_DIR / 'sample.json').read_text(encoding='utf-8')),
    }
