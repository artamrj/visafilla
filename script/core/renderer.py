"""Preflight and append vector/text overlays to the unmodified official pages."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import astuple, dataclass
from pathlib import Path

import pymupdf as fitz

from .coordinates import CHECKBOX_MAP, FIELD_MAP, OFFICIAL_USE, SIGNATURE, Field
from .paths import WORKSPACE_ROOT
from .schema import Applicant
from .utils import TEMPLATE, atomic_save, check_template


@dataclass(frozen=True)
class TextPlacement:
    key: str
    field: Field
    lines: list[str]
    size: float


def values_and_checks(applicant: Applicant) -> tuple[dict[str, str], list[str]]:
    """Translate semantic applicant data into measured field IDs and choices."""
    a = applicant
    values: dict[str, str] = {}
    checks: list[str] = []

    def flatten(prefix: str, obj: object) -> None:
        if hasattr(obj, 'model_dump'):
            obj = obj.model_dump()
        if isinstance(obj, dict):
            for key, value in obj.items():
                flatten(f'{prefix}.{key}' if prefix else key, value)
        elif prefix in FIELD_MAP and obj is not None:
            values[prefix] = ', '.join(obj) if isinstance(obj, list) else str(obj)

    flatten('', a)
    # Nationality at birth is requested only if different; retain JSON unchanged.
    if (
        a.personal.nationality_at_birth
        and a.personal.nationality_at_birth.casefold() == a.personal.current_nationality.casefold()
    ):
        values.pop('personal.nationality_at_birth', None)
    checks += [
        f'sex.{a.personal.sex}',
        f'marital.{a.personal.marital_status}',
        f'passport.{a.passport.type}',
        f'entries.{a.journey.entries_requested}',
        'residence.' + ('yes' if a.residence.lives_outside_country_of_nationality else 'no'),
    ]
    if a.previous_biometrics.fingerprints_taken is not None:
        checks.append('fingerprints.' + ('yes' if a.previous_biometrics.fingerprints_taken else 'no'))
    checks += ['purpose.' + p for p in a.journey.purposes]
    if a.guardian:
        g = a.guardian
        values['guardian'] = '\n'.join(
            filter(None, [f'{g.surname} {g.given_names}; {g.nationality}', g.address, f'{g.phone}; {g.email}'])
        )
    if a.eu_family_member:
        checks.append('relationship.' + a.eu_family_member.relationship)
    if a.occupation and a.occupation.employer_or_school:
        e = a.occupation.employer_or_school
        values['occupation.employer_or_school'] = '; '.join(filter(None, [e.name, e.address, e.phone]))
    if a.inviting_company:
        c = a.inviting_company
        values['inviting_company.name_address'] = f'{c.name}; {c.address}'
        values['inviting_company.contact'] = (
            f'{c.contact.surname} {c.contact.given_names}\n{c.contact.address}\n{c.contact.email}'
        )
    if a.expenses:
        e = a.expenses
        if e.applicant_means:
            checks.append('payer.applicant')
            checks += ['applicant.' + m for m in e.applicant_means]
        if e.sponsor_means:
            checks.append('payer.sponsor')
            checks += ['sponsor.' + m for m in e.sponsor_means]
        if e.sponsor:
            checks.append('sponsor_reference.' + ('other' if e.sponsor.reference == 'other' else 'form'))
    travel_notes = [a.journey.additional_information]
    stays = a.accommodation or []
    if stays:

        def labelled(stay, text):
            return f'{stay.city}: {text}' if stay.city else text

        def _stay_name_with_booking(stay):
            name = labelled(stay, stay.name)
            booking = []
            if stay.check_in and stay.check_out:
                booking.append(f'{stay.check_in} to {stay.check_out}')
            if stay.confirmation_code:
                booking.append(stay.confirmation_code)
            if booking:
                name = f'{name}: {"; ".join(booking)}'
            return name

        values['accommodation.name'] = '\n'.join(_stay_name_with_booking(stay) if stay else '' for stay in stays)
        values['accommodation.address'] = '\n'.join(
            labelled(
                stay,
                (
                    stay.address
                    if not stay.country or stay.address.rstrip(' .').casefold().endswith(stay.country.casefold())
                    else f'{stay.address}, {stay.country}'
                )
                + (f'; {stay.email}' if stay.email else ''),
            )
            for stay in stays
        )
        values['accommodation.phone'] = '\n'.join(labelled(stay, stay.phone) for stay in stays)
        travel_notes += [stay.booking_details for stay in stays if stay.booking_details]
    if any(travel_notes):
        values['journey.additional_information'] = '; '.join(filter(None, travel_notes))
    values['application.place_date'] = f'{a.application.place}\n{a.application.date}'
    # Preserve email spelling even when combined into guardian/company fields.
    for key, value in values.items():
        if key.endswith('.email'):
            continue
        values[key] = ''.join(part if '@' in part else part.upper() for part in re.split(r'([^\s;]+@[^\s;]+)', value))
    return {k: v for k, v in values.items() if v}, checks


def _wrap(text: str, width: float, font: fitz.Font, size: float, multiline: bool) -> list[str]:
    """Wrap at spaces, splitting long tokens only if necessary."""
    if not multiline:
        return [text.replace('\n', ' ')]
    lines: list[str] = []
    for paragraph in text.split('\n'):
        line = ''
        for word in paragraph.split():
            candidate = f'{line} {word}'.strip()
            if font.text_length(candidate, fontsize=size) <= width:
                line = candidate
                continue
            if line:
                lines.append(line)
                line = ''
            while font.text_length(word, fontsize=size) > width:
                n = 1
                while n < len(word) and font.text_length(word[: n + 1], fontsize=size) <= width:
                    n += 1
                if font.text_length(word[:n], fontsize=size) > width:
                    return [text]  # Cannot even fit one glyph; preflight rejects.
                lines.append(word[:n])
                word = word[n:]
            line = word
        lines.append(line)
    return lines


def fit_text(key: str, text: str, field: Field, font: fitz.Font) -> TextPlacement:
    """Check glyphs and find a legible size; never truncate or substitute text."""
    for c in text:
        if c == '\n':
            continue
        if unicodedata.bidirectional(c) in ('R', 'AL', 'AN') or unicodedata.combining(c):
            raise ValueError(
                f'{key}: script requires shaping not supported by this renderer; supply the passport Latin spelling'
            )
        # Conservatively reject complex scripts rather than render unshaped text.
        if unicodedata.category(c).startswith('L') and not any(
            s in unicodedata.name(c, '')
            for s in ('LATIN', 'GREEK', 'CYRILLIC', 'CJK', 'HIRAGANA', 'KATAKANA', 'HANGUL')
        ):
            raise ValueError(f'{key}: unsupported script shaping; supply a reliable Latin spelling')
        if not font.has_glyph(ord(c), fallback=False):
            raise ValueError(
                f'{key}: unsupported character U+{ord(c):04X}; use --font-file with a suitable local font or supply passport Latin spelling'
            )
    rect = fitz.Rect(field.rect)
    size = field.font_size
    while size >= field.min_font_size:
        lines = _wrap(text, rect.width, font, size, field.multiline)
        line_height = (field.line_spacing or (font.ascender - font.descender)) * size
        total_height = (font.ascender - font.descender) * size + (len(lines) - 1) * line_height
        if total_height <= rect.height and all(font.text_length(s, fontsize=size) <= rect.width for s in lines):
            return TextPlacement(key, field, lines, size)
        size = round(size - 0.25, 2)
    raise ValueError(
        f'{key}: text cannot fit within the measured field at {field.min_font_size:g} pt; shorten the value without omitting required information'
    )


def _check_geometry(doc: fitz.Document) -> None:
    """Fail if a coordinate change enters the protected column or leaves a page."""
    all_fields = list(FIELD_MAP.items()) + list(CHECKBOX_MAP.items()) + [('signature', SIGNATURE)]
    for key, field in all_fields:
        rect = fitz.Rect(field.rect)
        if rect.is_empty or not doc[field.page].rect.contains(rect):
            raise ValueError(f'{key}: invalid coordinate rectangle')
        if field.page == 0 and rect.intersects(fitz.Rect(OFFICIAL_USE.rect)):
            raise ValueError(f'{key}: coordinates enter official-use-only area')
    # Ignore whitespace and dotted answer lines, but protect every printed label
    # character's full font box. This also catches unsafe future coordinate edits.
    labels: dict[int, list[tuple[float, float, float, float]]] = {}
    for n, page in enumerate(doc):
        labels[n] = [
            tuple(c['bbox'])
            for block in page.get_text('rawdict')['blocks']
            for line in block.get('lines', [])
            for span in line['spans']
            for c in span['chars']
            if c['c'].strip() and c['c'] not in '.…□'
        ]
    for key, field in list(FIELD_MAP.items()) + [('signature', SIGNATURE)]:
        x0, y0, x1, y1 = field.rect
        if any(y0 < r[3] and y1 > r[1] and x0 < r[2] and x1 > r[0] for r in labels[field.page]):
            raise ValueError(f'{key}: writable rectangle intersects an original label')
    rules = {
        n: [d['rect'] for d in page.get_drawings() if d['rect'].width < 1 or d['rect'].height < 1]
        for n, page in enumerate(doc)
    }
    for key, field in all_fields:
        rect = fitz.Rect(field.rect)
        if any(rect.intersects(rule) for rule in rules[field.page]):
            raise ValueError(f'{key}: writable rectangle crosses an original form border')
    for i, (key, field) in enumerate(all_fields):
        for other_key, other in all_fields[i + 1 :]:
            if field.page == other.page and fitz.Rect(field.rect).intersects(fitz.Rect(other.rect)):
                raise ValueError(f'overlapping writable regions: {key}, {other_key}')


_geometry_identity: tuple | None = None


def _check_template_geometry() -> None:
    """Reuse successful checks only while template and all measured fields match."""
    global _geometry_identity
    identity = (
        check_template(),
        tuple((key, astuple(field)) for key, field in FIELD_MAP.items()),
        tuple((key, astuple(field)) for key, field in CHECKBOX_MAP.items()),
        astuple(SIGNATURE),
        astuple(OFFICIAL_USE),
    )
    if identity != _geometry_identity:
        with fitz.open(TEMPLATE) as doc:
            _check_geometry(doc)
        _geometry_identity = identity


def prepare(
    applicant: Applicant,
    source_dir: Path,
    font_file: Path | None = None,
    *,
    signature_bytes: bytes | None = None,
    allow_signature_path: bool = True,
) -> tuple[fitz.Font, list[TextPlacement], list[str], bytes | None]:
    """Validate template, text fit, coordinates and optional image before any save."""
    _check_template_geometry()
    font = fitz.Font(fontfile=str(font_file)) if font_file else fitz.Font('helv')
    values, checks = values_and_checks(applicant)
    placements = [fit_text(key, value, FIELD_MAP[key], font) for key, value in values.items()]
    for key in checks:
        if key not in CHECKBOX_MAP:
            raise ValueError(f'checkbox mapping missing: {key}')
    signature = signature_bytes
    if signature and not applicant.application.signature.enabled:
        raise ValueError('application.signature.enabled: enable the signature before attaching an image')
    if applicant.application.signature.enabled:
        if signature is None:
            if not allow_signature_path:
                raise ValueError(
                    'application.signature.image_path: reattach the signature using the local image picker'
                )
            path = (source_dir / str(applicant.application.signature.image_path)).resolve()
            if path.suffix.lower() not in ('.png', '.jpg', '.jpeg'):
                raise ValueError('application.signature.image_path: signature must be a local PNG or JPEG')
            signature = path.read_bytes()
        if not (signature.startswith(b'\x89PNG\r\n\x1a\n') or signature.startswith(b'\xff\xd8\xff')):
            raise ValueError('application.signature.image_path: signature must be PNG or JPEG')
        image = fitz.Pixmap(signature)
        if image.width == 0 or image.height == 0 or image.width * image.height > 16_000_000:
            raise ValueError('application.signature.image_path: signature image dimensions are invalid or too large')
    return font, placements, checks, signature


def fill_pdf(
    applicant: Applicant, target: Path, source_dir: Path, *, overwrite: bool = False, font_file: Path | None = None
) -> None:
    """Append preflighted overlays and atomically save a separate output PDF."""
    if target.resolve() == TEMPLATE.resolve() or target.resolve() == WORKSPACE_ROOT / 'Schengen-Form.pdf':
        raise ValueError('output must never be an original template')
    font, placements, checks, signature = prepare(applicant, source_dir, font_file)
    with fitz.open(TEMPLATE) as doc:
        _paint(doc, font, placements, checks, signature)
        atomic_save(doc, target, overwrite)


def _paint(
    doc: fitz.Document, font: fitz.Font, placements: list[TextPlacement], checks: list[str], signature: bytes | None
) -> None:
    """Shared painting path for the CLI and browser; original content is retained."""
    populated_pages: set[int] = set()
    for p in placements:
        page = doc[p.field.page]
        if p.field.page not in populated_pages:
            page.insert_font(fontname='ApplicantFont', fontbuffer=font.buffer)
            populated_pages.add(p.field.page)
        rect = fitz.Rect(p.field.rect)
        baseline = rect.y0 + font.ascender * p.size
        for line in p.lines:
            x = rect.x0
            if p.field.alignment == 'center':
                x += (rect.width - font.text_length(line, fontsize=p.size)) / 2
            elif p.field.alignment == 'right':
                x = rect.x1 - font.text_length(line, fontsize=p.size)
            page.insert_text(
                (x, baseline), line, fontname='ApplicantFont', fontsize=p.size, color=(0, 0, 0), overlay=True
            )
            baseline += (p.field.line_spacing or (font.ascender - font.descender)) * p.size
    for key in checks:
        field = CHECKBOX_MAP[key]
        rect = fitz.Rect(field.rect) + (0.65, 0.65, -0.65, -0.65)
        page = doc[field.page]
        page.draw_line(rect.tl, rect.br, color=(0, 0, 0), width=0.55, overlay=True)
        page.draw_line(rect.bl, rect.tr, color=(0, 0, 0), width=0.55, overlay=True)
    if signature:
        doc[SIGNATURE.page].insert_image(
            fitz.Rect(SIGNATURE.rect), stream=signature, keep_proportion=True, overlay=True
        )


def render_pdf_bytes(applicant: Applicant, *, signature_bytes: bytes | None = None) -> bytes:
    """Render in memory without allowing browser-supplied filesystem paths."""
    font, placements, checks, signature = prepare(
        applicant, Path('.'), signature_bytes=signature_bytes, allow_signature_path=False
    )
    with fitz.open(TEMPLATE) as doc:
        _paint(doc, font, placements, checks, signature)
        return doc.tobytes(garbage=0, deflate=False)


def calibrate(destination: Path, dpi: int = 300) -> None:
    """Write diagnostic PNGs and a coordinate index, never modify the template."""
    import json

    if not 72 <= dpi <= 600:
        raise ValueError('dpi must be between 72 and 600')
    destination.mkdir(parents=True, exist_ok=True)
    index = {}
    with fitz.open(TEMPLATE) as doc:
        for page in doc:
            for x in range(0, int(page.rect.width), 25):
                page.draw_line((x, 0), (x, page.rect.height), color=(0.7, 0.85, 1), width=0.2)
                page.insert_text((x + 1, 12), str(x), fontsize=5, color=(0, 0, 1))
            for y in range(25, int(page.rect.height), 25):
                page.draw_line((0, y), (page.rect.width, y), color=(0.7, 0.85, 1), width=0.2)
                page.insert_text((1, y), str(y), fontsize=5, color=(0, 0, 1))
        for n, (key, field) in enumerate(
            list(FIELD_MAP.items()) + list(CHECKBOX_MAP.items()) + [('signature', SIGNATURE)], 1
        ):
            page = doc[field.page]
            r = fitz.Rect(field.rect)
            color = (1, 0, 0) if key in CHECKBOX_MAP else (0, 0.45, 0)
            page.draw_rect(r, color=color, width=0.4)
            if key in CHECKBOX_MAP:
                page.draw_circle((r.tl + r.br) / 2, 0.4, color=color, fill=color)
            # Short numbered IDs remain legible on crowded rows; full names in index.
            page.insert_text((r.x0, r.y0 - 1), str(n), fontsize=4, color=color)
            index[str(n)] = {'field': key, 'page': field.page + 1, 'rect': list(field.rect)}
        for n, page in enumerate(doc, 1):
            page.get_pixmap(dpi=dpi).save(destination / f'page-{n}.png')
    (destination / 'field-index.json').write_text(json.dumps(index, indent=2) + '\n')
