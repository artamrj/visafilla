"""Resolve shared and country-specific blank applicant templates."""

from __future__ import annotations

import json
from pathlib import Path

from .paths import TEMPLATE_DIR


class TemplateError(ValueError):
    """Raised for malformed template definitions or invalid references."""


def _deep_merge(base: object, override: object) -> object:
    """Merge nested objects recursively; replace arrays and scalars whole."""
    if isinstance(base, dict) and isinstance(override, dict):
        result = dict(base)
        for key, value in override.items():
            result[key] = _deep_merge(result[key], value) if key in result else value
        return result
    return override


def load_country_template(country: str) -> dict:
    """Combine a country template with its shared base into one applicant dict.

    Country-only fields are placed under the resolved applicant's ``extras``
    object, omitted entirely when empty.
    """
    return _resolve(TEMPLATE_DIR / country / f'{country}.template.json', _seen=set())


def _resolve(path: Path, *, _seen: set[Path]) -> dict:
    path = path.resolve()
    if path in _seen:
        raise TemplateError(f'circular template reference: {path}')
    if path.parent != TEMPLATE_DIR.resolve() and not path.is_relative_to(TEMPLATE_DIR.resolve()):
        raise TemplateError(f'template reference outside template directory: {path}')
    _seen.add(path)
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError) as exc:
        raise TemplateError(f'cannot read template {path}: {exc}') from None
    if not isinstance(data, dict):
        raise TemplateError(f'template {path} must be a JSON object')

    extends = data.get('extends')
    if extends is not None:
        if not isinstance(extends, str) or not extends:
            raise TemplateError(f'template {path} has an invalid extends value')
        base_path = (path.parent / extends).resolve()
        base = _resolve(base_path, _seen=_seen)
    else:
        base = dict(data)

    overrides = data.get('overrides', {})
    extras = data.get('extras', {})
    for key in ('extends', 'overrides', 'extras'):
        base.pop(key, None)
    if not isinstance(overrides, dict) or not isinstance(extras, dict):
        raise TemplateError(f'template {path} overrides/extras must be objects')
    base = _deep_merge(base, overrides)
    if extras:
        base['extras'] = extras
    return base
