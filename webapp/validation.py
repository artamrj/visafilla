"""Reference rules for browser validation results: limits, error links and plain messages.

The in-browser engine (webapp/static/engine/) implements the same behaviour in JavaScript;
the parity tests compare both on every scenario, so keep them in step.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import ValidationError

from script.core.renderer import prepare
from script.core.schema import Applicant
from script.core.validator import parse_json_object
from webapp.fields import metadata

MAX_BODY = 3_000_000


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


def check(data: dict, signature: bytes | None = None) -> list[dict]:
    """Errors the browser shows for a validation request; empty when the form can be generated."""
    applicant, errors = validation_errors(data)
    if errors:
        return errors
    assert applicant is not None
    try:
        prepare(applicant, Path('.'), signature_bytes=signature, allow_signature_path=False)
    except ValueError as exc:
        message = str(exc)
        path = message.split(':', 1)[0]
        known = [f['path'] for f in metadata()['fields']]  # form order keeps the choice stable
        if path not in known:
            path = next((p for p in known if p.startswith(path + '.')), '')
        return [{'path': path, 'paths': [path] if path else [], 'message': message}]
    return []
