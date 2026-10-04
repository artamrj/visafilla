"""Measured PDF-point coordinates, top-left origin, zero-based pages.

Rectangles are writable interiors derived from original text bounds and vector
rules. Checkbox ink bounds are measured at 720 DPI; origins are extracted from
original square glyphs. See spain/layout_evidence.json for provenance.
"""

import json
from dataclasses import dataclass

from .paths import SPAIN_FORM_DIR


@dataclass(frozen=True)
class Field:
    """A writable interior; font size shrinks only as far as min_font_size."""

    page: int
    rect: tuple[float, float, float, float]
    font_size: float = 9
    min_font_size: float = 6
    alignment: str = 'left'
    multiline: bool = True
    line_spacing: float | None = None


FIELD_MAP: dict[str, Field] = {
    'personal.surname': Field(0, (51, 202, 448, 224)),
    'personal.surname_at_birth': Field(0, (51, 239, 448, 261)),
    'personal.given_names': Field(0, (51, 277, 448, 298)),
    'personal.date_of_birth': Field(0, (51, 324, 180, 338)),
    'personal.place_of_birth': Field(0, (185, 314, 313, 336)),
    'personal.country_of_birth': Field(0, (185, 351, 313, 373)),
    'personal.current_nationality': Field(0, (319, 322, 448, 337)),
    'personal.nationality_at_birth': Field(0, (319, 359, 448, 374)),
    'personal.other_nationalities': Field(0, (319, 387, 448, 401)),
    'personal.marital_status_other': Field(0, (338, 452, 448, 466)),
    'guardian': Field(0, (51, 508, 448, 549)),
    'personal.national_id': Field(0, (51, 563, 448, 577)),
    'passport.type_other': Field(0, (51, 627, 448, 638)),
    'passport.number': Field(0, (51, 661, 167, 675)),
    'passport.date_of_issue': Field(0, (172, 661, 250, 675)),
    'passport.valid_until': Field(0, (255, 661, 329, 675)),
    'passport.issued_by': Field(0, (334, 661, 448, 675)),
    'eu_family_member.surname': Field(0, (51, 727, 247, 758)),
    'eu_family_member.given_names': Field(0, (252, 727, 448, 758)),
    'eu_family_member.date_of_birth': Field(1, (51, 71, 211, 92)),
    'eu_family_member.nationality': Field(1, (217, 71, 377, 92)),
    'eu_family_member.document_number': Field(1, (382, 71, 543, 92)),
    'eu_family_member.relationship_other': Field(1, (140, 124, 543, 139)),
    'contact.home_address': Field(1, (51, 162, 294, 181), min_font_size=5.5, line_spacing=1.2),
    'contact.email': Field(1, (51, 182, 294, 194)),
    'contact.phone': Field(1, (300, 154, 543, 191)),
    # Inline dotted answer lines: text sits above the dots, away from labels.
    'residence.permit_type': Field(1, (342, 223.5, 433, 232.4), 7),
    'residence.permit_number': Field(1, (473, 223.5, 535, 232.4), 7),
    'residence.valid_until': Field(1, (137.5, 234.3, 251, 242.6), 7),
    'occupation.current_occupation': Field(1, (51, 265, 543, 278)),
    'occupation.employer_or_school': Field(1, (51, 300.5, 543, 317.5)),
    'journey.purpose_other': Field(1, (51, 358, 543, 371)),
    'journey.additional_information': Field(1, (51, 384, 543, 402.1), min_font_size=5.5, line_spacing=1.2),
    'journey.main_destination': Field(1, (51, 434, 294, 474)),
    'journey.first_entry_country': Field(1, (300, 416, 543, 474)),
    # Arrival has a single narrow blank row between bilingual labels.
    'journey.arrival_date': Field(1, (51, 523.4, 190, 532.4), 7),
    'journey.departure_date': Field(1, (102, 547, 245, 558)),
    'previous_biometrics.date': Field(1, (162, 585.8, 228, 595.5), 7),
    'previous_biometrics.visa_sticker_number': Field(1, (435, 585.8, 543, 595.5), 7),
    'final_destination_permit.issued_by': Field(1, (129, 623.2, 229, 632.8), 7),
    'final_destination_permit.valid_from': Field(1, (313, 623.2, 404, 632.8), 7),
    'final_destination_permit.valid_until': Field(1, (445, 623.2, 542, 632.8), 7),
    'accommodation.name': Field(1, (51, 670, 543, 692), min_font_size=5.5, line_spacing=1.2),
    'accommodation.address': Field(1, (51, 735, 294, 776), min_font_size=5.5, line_spacing=1.2),
    'accommodation.phone': Field(1, (300, 708, 543, 742)),
    'inviting_company.name_address': Field(2, (51, 58.4, 543, 68.4), 7),
    'inviting_company.contact': Field(2, (51, 101, 294, 138)),
    'inviting_company.phone': Field(2, (300, 92, 543, 138)),
    'expenses.sponsor.name': Field(2, (397, 199.5, 544, 207.8), 7),
    'expenses.applicant_other': Field(2, (58, 267, 275, 298)),
    'expenses.sponsor_other': Field(2, (445, 283, 544, 299), 7),
    'application.place_date': Field(3, (51, 479, 294, 542)),
}
SIGNATURE = Field(3, (301, 499, 543, 541))
OFFICIAL_USE = Field(0, (450.94, 189.5, 547.56, 761.38))
CHECKBOX_MAP: dict[str, Field] = {
    key: Field(value['page'], tuple(value['rect']))
    for key, value in json.loads((SPAIN_FORM_DIR / 'checkboxes.json').read_text()).items()
}
