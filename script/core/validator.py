"""Local JSON loading with actionable errors that do not echo personal data."""

import json
from pathlib import Path

from pydantic import ValidationError

from .schema import Applicant


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f'duplicate JSON key: {key}')
        result[key] = value
    return result


def parse_json_object(text: str) -> dict[str, object]:
    """Parse an applicant object using the same strict rules for every interface."""

    def reject_constant(value: str) -> None:
        raise ValueError('JSON cannot contain non-finite numbers')

    try:
        raw = json.loads(text, object_pairs_hook=_unique_object, parse_constant=reject_constant)
    except json.JSONDecodeError as exc:
        raise ValueError(f'Invalid JSON at line {exc.lineno}, column {exc.colno}: {exc.msg}') from None
    if not isinstance(raw, dict):
        raise ValueError('JSON must contain an applicant object')
    return raw


def load_applicant(path: Path) -> Applicant:
    """Load UTF-8 JSON, rejecting duplicate keys and contradictory inputs."""
    try:
        return Applicant.model_validate(parse_json_object(path.read_text(encoding='utf-8')))
    except ValidationError as exc:
        messages = [
            f"{'.'.join(map(str, e['loc'])) or 'application'}: {e['msg']}" for e in exc.errors(include_input=False)
        ]
        raise ValueError('\n'.join(messages)) from None
