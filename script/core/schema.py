"""Semantic, strict input models. Dates stay in the form's printed format."""

from __future__ import annotations

import re
import unicodedata
from datetime import date, datetime
from typing import Annotated, Literal, Self

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, StringConstraints, field_validator, model_validator


def clean_text(value: str) -> str:
    """Reject invisible controls; normalize Unicode without transliteration."""
    value = value.replace('\r\n', '\n')
    if any(c != '\n' and unicodedata.category(c).startswith('C') for c in value):
        raise ValueError('control characters are not allowed')
    return unicodedata.normalize('NFC', value)


Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1), AfterValidator(clean_text)]


def parse_date(value: str) -> date:
    """Parse an exact DD-MM-YYYY date, including calendar validation."""
    if not re.fullmatch(r'\d{2}-\d{2}-\d{4}', value, flags=re.ASCII):
        raise ValueError('date must use DD-MM-YYYY')
    try:
        return datetime.strptime(value, '%d-%m-%Y').date()
    except ValueError:
        raise ValueError('date is not a valid calendar date') from None


def check_date(value: str) -> str:
    parse_date(value)
    return value


DateText = Annotated[str, StringConstraints(pattern=r'^[0-9]{2}-[0-9]{2}-[0-9]{4}$'), AfterValidator(check_date)]
Sex = Literal['male', 'female']
Marital = Literal['single', 'married', 'registered_union', 'separated', 'divorced', 'widowed', 'other']
PassportType = Literal['ordinary', 'diplomatic', 'service', 'official', 'special', 'other']
Relationship = Literal['spouse', 'child', 'grandchild', 'dependent_ascendant', 'registered_partnership', 'other']
Purpose = Literal[
    'tourism',
    'business',
    'visiting_family_or_friends',
    'cultural',
    'sports',
    'official_visit',
    'medical',
    'study',
    'airport_transit',
    'other',
]
ApplicantMeans = Literal[
    'cash', 'travellers_cheques', 'credit_card', 'prepaid_accommodation', 'prepaid_transport', 'other'
]
SponsorMeans = Literal['cash', 'accommodation_provided', 'all_expenses_covered', 'prepaid_transport', 'other']


def other_detail(selected: bool, detail: str | None, name: str) -> None:
    """Require an explanation exactly when the other checkbox is selected."""
    if selected != (detail is not None):
        raise ValueError(f'{name} must be supplied exactly when other is selected')


class Model(BaseModel):
    """No implicit coercion or silently ignored keys."""

    model_config = ConfigDict(extra='forbid', strict=True)

    @model_validator(mode='after')
    def unique_lists(self) -> Self:
        for key in type(self).model_fields:
            value = getattr(self, key)
            if isinstance(value, list) and any(item in value[:i] for i, item in enumerate(value)):
                raise ValueError(f'{key} contains duplicate values')
        return self


class Personal(Model):
    surname: Text
    surname_at_birth: Text | None = None
    given_names: Text
    date_of_birth: DateText
    place_of_birth: Text
    country_of_birth: Text
    current_nationality: Text
    nationality_at_birth: Text | None = None
    other_nationalities: list[Text] = Field(default_factory=list)
    sex: Sex
    marital_status: Marital
    marital_status_other: Text | None = None
    national_id: Text | None = None

    @model_validator(mode='after')
    def details(self) -> Self:
        other_detail(self.marital_status == 'other', self.marital_status_other, 'marital_status_other')
        return self


class Passport(Model):
    type: PassportType
    type_other: Text | None = None
    number: Text
    date_of_issue: DateText
    valid_until: DateText
    issued_by: Text

    @model_validator(mode='after')
    def details(self) -> Self:
        other_detail(self.type == 'other', self.type_other, 'passport.type_other')
        if parse_date(self.date_of_issue) >= parse_date(self.valid_until):
            raise ValueError('passport valid_until must follow date_of_issue')
        return self


class Contact(Model):
    home_address: Text
    email: Text
    phone: Text

    @model_validator(mode='after')
    def email_syntax(self) -> Self:
        validate_email(self.email)
        return self


def validate_email(value: str) -> None:
    """Local syntax check only; never resolve DNS or contact an email service."""
    if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', value):
        raise ValueError('invalid email address syntax')


class Guardian(Model):
    surname: Text
    given_names: Text
    address: Text | None = None
    phone: Text
    email: Text
    nationality: Text

    @model_validator(mode='after')
    def email_syntax(self) -> Self:
        validate_email(self.email)
        return self


class EUFamilyMember(Model):
    surname: Text
    given_names: Text
    date_of_birth: DateText
    nationality: Text
    document_number: Text
    relationship: Relationship
    relationship_other: Text | None = None

    @model_validator(mode='after')
    def details(self) -> Self:
        other_detail(self.relationship == 'other', self.relationship_other, 'relationship_other')
        return self


class Residence(Model):
    lives_outside_country_of_nationality: bool
    permit_type: Text | None = None
    permit_number: Text | None = None
    valid_until: DateText | None = None

    @model_validator(mode='after')
    def details(self) -> Self:
        values = [self.permit_type, self.permit_number, self.valid_until]
        if not self.lives_outside_country_of_nationality and any(v is not None for v in values):
            raise ValueError('residence=false contradicts populated permit details')
        if self.lives_outside_country_of_nationality and not all(values):
            raise ValueError('residence=true requires permit_type, permit_number and valid_until')
        return self


class Employer(Model):
    name: Text
    address: Text
    phone: Text | None = None


class Occupation(Model):
    current_occupation: Text
    employer_or_school: Employer | None = None


class Journey(Model):
    purposes: list[Purpose] = Field(min_length=1)
    purpose_other: Text | None = None
    additional_information: Text | None = None
    main_destination: list[Text] = Field(min_length=1)
    first_entry_country: Text
    entries_requested: Literal['single', 'double', 'multiple']
    arrival_date: DateText
    departure_date: DateText

    @model_validator(mode='after')
    def details(self) -> Self:
        if not self.purposes or not self.main_destination:
            raise ValueError('purposes and main_destination cannot be empty')
        other_detail('other' in self.purposes, self.purpose_other, 'purpose_other')
        if parse_date(self.departure_date) < parse_date(self.arrival_date):
            raise ValueError('departure_date must not precede arrival_date')
        return self


class Biometrics(Model):
    fingerprints_taken: bool | None
    date: DateText | None = None
    visa_sticker_number: Text | None = None
    visa_issuing_country: Text | None = None
    visa_entry_date: DateText | None = None

    @model_validator(mode='after')
    def details(self) -> Self:
        if self.fingerprints_taken is False and (self.date or self.visa_sticker_number):
            raise ValueError('fingerprints_taken=false contradicts fingerprint date/visa number')
        if self.fingerprints_taken is None and self.date:
            raise ValueError('fingerprint date requires fingerprints_taken=true')
        return self


class EntryPermit(Model):
    issued_by: Text
    valid_from: DateText
    valid_until: DateText

    @model_validator(mode='after')
    def details(self) -> Self:
        if parse_date(self.valid_until) < parse_date(self.valid_from):
            raise ValueError('entry permit valid_until precedes valid_from')
        return self


class Accommodation(Model):
    country: Text | None = None
    city: Text | None = None
    check_in: DateText | None = None
    check_out: DateText | None = None
    confirmation_code: Text | None = None
    booking_details: Text | None = None
    type: Literal['hotel', 'inviting_person', 'temporary_accommodation']
    name: Text
    address: Text
    email: Text | None = None
    phone: Text

    @model_validator(mode='after')
    def email_syntax(self) -> Self:
        if self.email:
            for line in self.email.splitlines():
                validate_email(line.rsplit(":", 1)[-1].strip())
        return self


class CompanyContact(Model):
    surname: Text
    given_names: Text
    address: Text
    email: Text

    @model_validator(mode='after')
    def email_syntax(self) -> Self:
        validate_email(self.email)
        return self


class InvitingCompany(Model):
    name: Text
    address: Text
    contact: CompanyContact
    phone: Text


class Sponsor(Model):
    reference: Literal['field_30', 'field_31', 'other']
    name: Text | None = None

    @model_validator(mode='after')
    def details(self) -> Self:
        other_detail(self.reference == 'other', self.name, 'sponsor.name')
        return self


class Expenses(Model):
    paid_by: Literal['applicant', 'sponsor', 'shared']
    applicant_means: list[ApplicantMeans] = Field(default_factory=list)
    sponsor_means: list[SponsorMeans] = Field(default_factory=list)
    applicant_other: Text | None = None
    sponsor_other: Text | None = None
    sponsor: Sponsor | None = None

    @model_validator(mode='after')
    def details(self) -> Self:
        own = self.paid_by in ('applicant', 'shared')
        sponsored = self.paid_by in ('sponsor', 'shared')
        if own != bool(self.applicant_means):
            raise ValueError('applicant_means must be populated exactly for applicant/shared funding')
        if sponsored != bool(self.sponsor_means) or sponsored != (self.sponsor is not None):
            raise ValueError('sponsor funding requires sponsor and sponsor_means; applicant-only funding forbids them')
        other_detail('other' in self.applicant_means, self.applicant_other, 'applicant_other')
        other_detail('other' in self.sponsor_means, self.sponsor_other, 'sponsor_other')
        if self.paid_by == 'shared' and 'all_expenses_covered' in self.sponsor_means:
            raise ValueError('shared funding contradicts sponsor all_expenses_covered')
        return self


class Signature(Model):
    enabled: bool = False
    image_path: Text | None = None

    @model_validator(mode='after')
    def details(self) -> Self:
        if self.enabled != (self.image_path is not None):
            raise ValueError('signature image_path is required exactly when enabled=true')
        return self


class Application(Model):
    place: Text
    date: DateText
    signature: Signature = Field(default_factory=Signature)


class Applicant(Model):
    personal: Personal
    passport: Passport
    contact: Contact
    residence: Residence
    occupation: Occupation | None = None
    journey: Journey
    previous_biometrics: Biometrics
    accommodation: list[Accommodation] | None = Field(default=None, min_length=1)
    expenses: Expenses | None = None
    application: Application
    guardian: Guardian | None = None
    eu_family_member: EUFamilyMember | None = None
    eu_family_exemption: bool = False
    inviting_company: InvitingCompany | None = None
    final_destination_permit: EntryPermit | None = None

    @field_validator('accommodation', mode='before')
    @classmethod
    def legacy_accommodation(cls, value):
        # Older single-object JSON imports remain supported. Exports use arrays.
        return [value] if isinstance(value, dict) else value

    @model_validator(mode='after')
    def consistency(self) -> Self:
        birth = parse_date(self.personal.date_of_birth)
        applied = parse_date(self.application.date)
        arrival = parse_date(self.journey.arrival_date)
        if birth >= applied:
            raise ValueError('date_of_birth must precede application.date')
        age = applied.year - birth.year - ((applied.month, applied.day) < (birth.month, birth.day))
        if (age < 18) != (self.guardian is not None):
            raise ValueError('guardian must be supplied for minors only (age at application date)')
        if not birth <= parse_date(self.passport.date_of_issue) <= applied <= arrival:
            raise ValueError('expected birth <= passport issue <= application date <= arrival')
        if parse_date(self.passport.valid_until) < parse_date(self.journey.departure_date):
            raise ValueError('passport expires before departure')
        if self.previous_biometrics.date and not birth <= parse_date(self.previous_biometrics.date) <= applied:
            raise ValueError('fingerprint date must be between birth and application date')
        if self.residence.valid_until and parse_date(self.residence.valid_until) < applied:
            raise ValueError('residence permit expires before application date')
        if self.eu_family_member and parse_date(self.eu_family_member.date_of_birth) >= applied:
            raise ValueError('EU family member birth must precede application date')
        if self.eu_family_exemption:
            if not self.eu_family_member:
                raise ValueError('EU family exemption requires eu_family_member')
            if any(v is not None for v in (self.occupation, self.accommodation, self.inviting_company, self.expenses)):
                raise ValueError('EU family exemption requires fields 21, 22, 30, 31, 32 to be absent')
        elif not self.occupation or not self.expenses or not (self.accommodation or self.inviting_company):
            raise ValueError(
                'non-exempt applications require occupation, expenses, and accommodation or inviting_company'
            )
        for stay in self.accommodation or []:
            if bool(stay.check_in) != bool(stay.check_out):
                raise ValueError('accommodation requires both check_in and check_out when dates are supplied')
            if stay.check_in and not arrival <= parse_date(stay.check_in) < parse_date(stay.check_out) <= parse_date(
                self.journey.departure_date
            ):
                raise ValueError('accommodation dates must be within the journey and check_out must follow check_in')
        if self.expenses and self.expenses.sponsor:
            ref = self.expenses.sponsor.reference
            if ref == 'field_30' and not self.accommodation:
                raise ValueError('sponsor field_30 requires accommodation/inviting person')
            if ref == 'field_31' and not self.inviting_company:
                raise ValueError('sponsor field_31 requires inviting_company')
        return self
