// Applicant validation in the browser: a faithful port of script/core/schema.py (Pydantic,
// strict mode) plus the error linking of webapp/validation.py. Parity tests compare both.

const INVALID = Symbol("invalid");
const PATTERN = "^[0-9]{2}-[0-9]{2}-[0-9]{4}$";

// ----- Field types -------------------------------------------------------------------
const text = { kind: "text" };
const date = { kind: "date" };
const bool = { kind: "bool" };
const lit = (...values) => ({ kind: "literal", values });
const list = (item, min = 0) => ({ kind: "list", item, min });
const opt = (type) => ({ ...type, nullable: true });
const model = (name, fields, validators = []) => ({ kind: "model", name, fields, validators });
// A field is [name, type] (required) or [name, type, () => default].
const none = () => null;

function parseDate(value) {
  if (!/^[0-9]{2}-[0-9]{2}-[0-9]{4}$/.test(value)) throw new Error("date must use DD-MM-YYYY");
  const [d, m, y] = value.split("-").map(Number);
  const when = new Date(Date.UTC(y, m - 1, d));
  if (y < 1 || when.getUTCFullYear() !== y || when.getUTCMonth() !== m - 1 || when.getUTCDate() !== d)
    throw new Error("date is not a valid calendar date");
  return y * 10000 + m * 100 + d; // comparable number
}

function otherDetail(selected, detail, name) {
  if (selected !== (detail !== null)) throw new Error(`${name} must be supplied exactly when other is selected`);
}

function validateEmail(value) {
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/u.test(value)) throw new Error("invalid email address syntax");
}

function uniqueLists(obj, spec) {
  for (const [key] of spec.fields) {
    const value = obj[key];
    if (Array.isArray(value) && value.some((item, i) => value.indexOf(item) < i))
      throw new Error(`${key} contains duplicate values`);
  }
}

// ----- Models, in the same field order as schema.py ----------------------------------
const Personal = model(
  "Personal",
  [
    ["surname", text],
    ["surname_at_birth", opt(text), none],
    ["given_names", text],
    ["date_of_birth", date],
    ["place_of_birth", text],
    ["country_of_birth", text],
    ["current_nationality", text],
    ["nationality_at_birth", opt(text), none],
    ["other_nationalities", list(text), () => []],
    ["sex", lit("male", "female")],
    ["marital_status", lit("single", "married", "registered_union", "separated", "divorced", "widowed", "other")],
    ["marital_status_other", opt(text), none],
    ["national_id", opt(text), none],
  ],
  [(s) => otherDetail(s.marital_status === "other", s.marital_status_other, "marital_status_other")],
);
const Passport = model(
  "Passport",
  [
    ["type", lit("ordinary", "diplomatic", "service", "official", "special", "other")],
    ["type_other", opt(text), none],
    ["number", text],
    ["date_of_issue", date],
    ["valid_until", date],
    ["issued_by", text],
  ],
  [
    (s) => {
      otherDetail(s.type === "other", s.type_other, "passport.type_other");
      if (parseDate(s.date_of_issue) >= parseDate(s.valid_until))
        throw new Error("passport valid_until must follow date_of_issue");
    },
  ],
);
const Contact = model(
  "Contact",
  [
    ["home_address", text],
    ["email", text],
    ["phone", text],
  ],
  [(s) => validateEmail(s.email)],
);
const Guardian = model(
  "Guardian",
  [
    ["surname", text],
    ["given_names", text],
    ["address", opt(text), none],
    ["phone", text],
    ["email", text],
    ["nationality", text],
  ],
  [(s) => validateEmail(s.email)],
);
const EUFamilyMember = model(
  "EUFamilyMember",
  [
    ["surname", text],
    ["given_names", text],
    ["date_of_birth", date],
    ["nationality", text],
    ["document_number", text],
    ["relationship", lit("spouse", "child", "grandchild", "dependent_ascendant", "registered_partnership", "other")],
    ["relationship_other", opt(text), none],
  ],
  [(s) => otherDetail(s.relationship === "other", s.relationship_other, "relationship_other")],
);
const Residence = model(
  "Residence",
  [
    ["lives_outside_country_of_nationality", bool],
    ["permit_type", opt(text), none],
    ["permit_number", opt(text), none],
    ["valid_until", opt(date), none],
  ],
  [
    (s) => {
      const values = [s.permit_type, s.permit_number, s.valid_until];
      if (!s.lives_outside_country_of_nationality && values.some((v) => v !== null))
        throw new Error("residence=false contradicts populated permit details");
      if (s.lives_outside_country_of_nationality && !values.every(Boolean))
        throw new Error("residence=true requires permit_type, permit_number and valid_until");
    },
  ],
);
const Employer = model("Employer", [
  ["name", text],
  ["address", text],
  ["phone", opt(text), none],
]);
const Occupation = model("Occupation", [
  ["current_occupation", text],
  ["employer_or_school", opt(Employer), none],
]);
const PURPOSES = [
  "tourism",
  "business",
  "visiting_family_or_friends",
  "cultural",
  "sports",
  "official_visit",
  "medical",
  "study",
  "airport_transit",
  "other",
];
const Journey = model(
  "Journey",
  [
    ["purposes", list(lit(...PURPOSES), 1)],
    ["purpose_other", opt(text), none],
    ["additional_information", opt(text), none],
    ["main_destination", list(text, 1)],
    ["first_entry_country", text],
    ["entries_requested", lit("single", "double", "multiple")],
    ["arrival_date", date],
    ["departure_date", date],
  ],
  [
    (s) => {
      if (!s.purposes.length || !s.main_destination.length)
        throw new Error("purposes and main_destination cannot be empty");
      otherDetail(s.purposes.includes("other"), s.purpose_other, "purpose_other");
      if (parseDate(s.departure_date) < parseDate(s.arrival_date))
        throw new Error("departure_date must not precede arrival_date");
    },
  ],
);
const Biometrics = model(
  "Biometrics",
  [
    ["fingerprints_taken", opt(bool)],
    ["date", opt(date), none],
    ["visa_sticker_number", opt(text), none],
    ["visa_issuing_country", opt(text), none],
    ["visa_entry_date", opt(date), none],
  ],
  [
    (s) => {
      if (s.fingerprints_taken === false && (s.date || s.visa_sticker_number))
        throw new Error("fingerprints_taken=false contradicts fingerprint date/visa number");
      if (s.fingerprints_taken === null && s.date) throw new Error("fingerprint date requires fingerprints_taken=true");
    },
  ],
);
const EntryPermit = model(
  "EntryPermit",
  [
    ["issued_by", text],
    ["valid_from", date],
    ["valid_until", date],
  ],
  [
    (s) => {
      if (parseDate(s.valid_until) < parseDate(s.valid_from)) throw new Error("entry permit valid_until precedes valid_from");
    },
  ],
);
const Accommodation = model(
  "Accommodation",
  [
    ["country", opt(text), none],
    ["city", opt(text), none],
    ["check_in", opt(date), none],
    ["check_out", opt(date), none],
    ["confirmation_code", opt(text), none],
    ["booking_details", opt(text), none],
    ["type", lit("hotel", "inviting_person", "temporary_accommodation")],
    ["name", text],
    ["address", text],
    ["email", opt(text), none],
    ["phone", text],
  ],
  [
    (s) => {
      if (s.email) for (const line of s.email.split(/\r\n|\n|\r/)) validateEmail(line.split(":").at(-1).trim());
    },
  ],
);
const CompanyContact = model(
  "CompanyContact",
  [
    ["surname", text],
    ["given_names", text],
    ["address", text],
    ["email", text],
  ],
  [(s) => validateEmail(s.email)],
);
const InvitingCompany = model("InvitingCompany", [
  ["name", text],
  ["address", text],
  ["contact", CompanyContact],
  ["phone", text],
]);
const Sponsor = model(
  "Sponsor",
  [
    ["reference", lit("field_30", "field_31", "other")],
    ["name", opt(text), none],
  ],
  [(s) => otherDetail(s.reference === "other", s.name, "sponsor.name")],
);
const Expenses = model(
  "Expenses",
  [
    ["paid_by", lit("applicant", "sponsor", "shared")],
    ["applicant_means", list(lit("cash", "travellers_cheques", "credit_card", "prepaid_accommodation", "prepaid_transport", "other")), () => []],
    ["sponsor_means", list(lit("cash", "accommodation_provided", "all_expenses_covered", "prepaid_transport", "other")), () => []],
    ["applicant_other", opt(text), none],
    ["sponsor_other", opt(text), none],
    ["sponsor", opt(Sponsor), none],
  ],
  [
    (s) => {
      const own = ["applicant", "shared"].includes(s.paid_by);
      const sponsored = ["sponsor", "shared"].includes(s.paid_by);
      if (own !== s.applicant_means.length > 0)
        throw new Error("applicant_means must be populated exactly for applicant/shared funding");
      if (sponsored !== s.sponsor_means.length > 0 || sponsored !== (s.sponsor !== null))
        throw new Error("sponsor funding requires sponsor and sponsor_means; applicant-only funding forbids them");
      otherDetail(s.applicant_means.includes("other"), s.applicant_other, "applicant_other");
      otherDetail(s.sponsor_means.includes("other"), s.sponsor_other, "sponsor_other");
      if (s.paid_by === "shared" && s.sponsor_means.includes("all_expenses_covered"))
        throw new Error("shared funding contradicts sponsor all_expenses_covered");
    },
  ],
);
const Signature = model(
  "Signature",
  [
    ["enabled", bool, () => false],
    ["image_path", opt(text), none],
  ],
  [
    (s) => {
      if (s.enabled !== (s.image_path !== null)) throw new Error("signature image_path is required exactly when enabled=true");
    },
  ],
);
const Application = model("Application", [
  ["place", text],
  ["date", date],
  ["signature", Signature, () => ({ enabled: false, image_path: null })],
]);

function consistency(s) {
  const birth = parseDate(s.personal.date_of_birth);
  const applied = parseDate(s.application.date);
  const arrival = parseDate(s.journey.arrival_date);
  if (birth >= applied) throw new Error("date_of_birth must precede application.date");
  // Dates are YYYYMMDD numbers, so whole years of age come from integer division.
  const age = Math.floor((applied - birth) / 10000);
  if (age < 18 !== (s.guardian !== null)) throw new Error("guardian must be supplied for minors only (age at application date)");
  const issued = parseDate(s.passport.date_of_issue);
  if (!(birth <= issued && issued <= applied && applied <= arrival))
    throw new Error("expected birth <= passport issue <= application date <= arrival");
  if (parseDate(s.passport.valid_until) < parseDate(s.journey.departure_date)) throw new Error("passport expires before departure");
  if (s.previous_biometrics.date) {
    const taken = parseDate(s.previous_biometrics.date);
    if (!(birth <= taken && taken <= applied)) throw new Error("fingerprint date must be between birth and application date");
  }
  if (s.residence.valid_until && parseDate(s.residence.valid_until) < applied)
    throw new Error("residence permit expires before application date");
  if (s.eu_family_member && parseDate(s.eu_family_member.date_of_birth) >= applied)
    throw new Error("EU family member birth must precede application date");
  if (s.eu_family_exemption) {
    if (!s.eu_family_member) throw new Error("EU family exemption requires eu_family_member");
    if ([s.occupation, s.accommodation, s.inviting_company, s.expenses].some((v) => v !== null))
      throw new Error("EU family exemption requires fields 21, 22, 30, 31, 32 to be absent");
  } else if (!s.occupation || !s.expenses || !(s.accommodation || s.inviting_company)) {
    throw new Error("non-exempt applications require occupation, expenses, and accommodation or inviting_company");
  }
  const departure = parseDate(s.journey.departure_date);
  for (const stay of s.accommodation || []) {
    if (Boolean(stay.check_in) !== Boolean(stay.check_out))
      throw new Error("accommodation requires both check_in and check_out when dates are supplied");
    if (stay.check_in) {
      const start = parseDate(stay.check_in),
        end = parseDate(stay.check_out);
      if (!(arrival <= start && start < end && end <= departure))
        throw new Error("accommodation dates must be within the journey and check_out must follow check_in");
    }
  }
  if (s.expenses && s.expenses.sponsor) {
    const ref = s.expenses.sponsor.reference;
    if (ref === "field_30" && !s.accommodation) throw new Error("sponsor field_30 requires accommodation/inviting person");
    if (ref === "field_31" && !s.inviting_company) throw new Error("sponsor field_31 requires inviting_company");
  }
}

export const ApplicantModel = model(
  "Applicant",
  [
    ["personal", Personal],
    ["passport", Passport],
    ["contact", Contact],
    ["residence", Residence],
    ["occupation", opt(Occupation), none],
    ["journey", Journey],
    ["previous_biometrics", Biometrics],
    ["accommodation", opt(list(Accommodation, 1)), none],
    ["expenses", opt(Expenses), none],
    ["application", Application],
    ["guardian", opt(Guardian), none],
    ["eu_family_member", opt(EUFamilyMember), none],
    ["eu_family_exemption", bool, () => false],
    ["inviting_company", opt(InvitingCompany), none],
    ["final_destination_permit", opt(EntryPermit), none],
  ],
  [consistency],
);

// ----- Validation engine --------------------------------------------------------------
function cleanText(value) {
  value = value.replaceAll("\r\n", "\n");
  for (const c of value) if (c !== "\n" && /\p{C}/u.test(c)) throw new Error("control characters are not allowed");
  return value.normalize("NFC");
}

function check(type, value, loc, errors) {
  if (value === null && type.nullable) return null;
  const add = (kind, msg, extra = {}) => {
    errors.push({ type: kind, loc, msg, input: value, ...extra });
    return INVALID;
  };
  switch (type.kind) {
    case "text": {
      if (typeof value !== "string") return add("string_type", "Input should be a valid string");
      const stripped = value.trim();
      if (!stripped.length) return add("string_too_short", "String should have at least 1 character");
      try {
        return cleanText(stripped);
      } catch (e) {
        return add("value_error", "Value error, " + e.message);
      }
    }
    case "date": {
      if (typeof value !== "string") return add("string_type", "Input should be a valid string");
      if (!new RegExp(PATTERN).test(value))
        return add("string_pattern_mismatch", `String should match pattern '${PATTERN}'`, { ctx: { pattern: PATTERN } });
      try {
        parseDate(value);
        return value;
      } catch (e) {
        return add("value_error", "Value error, " + e.message);
      }
    }
    case "bool":
      return typeof value === "boolean" ? value : add("bool_type", "Input should be a valid boolean");
    case "literal":
      return type.values.includes(value) ? value : add("literal_error", "Input should be one of the listed options");
    case "list": {
      if (!Array.isArray(value)) return add("list_type", "Input should be a valid list");
      const before = errors.length;
      const items = value.map((item, i) => check(type.item, item, [...loc, i], errors));
      if (errors.length > before) return INVALID;
      if (items.length < type.min)
        return add("too_short", `List should have at least ${type.min} item after validation, not ${items.length}`);
      return items;
    }
    case "model": {
      if (!value || typeof value !== "object" || Array.isArray(value))
        return add("model_type", `Input should be a valid dictionary or instance of ${type.name}`);
      const before = errors.length;
      const result = {};
      for (const [key, fieldType, fallback] of type.fields) {
        if (!Object.hasOwn(value, key)) {
          if (fallback) result[key] = fallback();
          else errors.push({ type: "missing", loc: [...loc, key], msg: "Field required", input: value });
          continue;
        }
        let input = value[key];
        // Older single-object accommodation imports are still accepted.
        if (type === ApplicantModel && key === "accommodation" && input && typeof input === "object" && !Array.isArray(input))
          input = [input];
        result[key] = check(fieldType, input, [...loc, key], errors);
      }
      const known = new Set(type.fields.map(([key]) => key));
      for (const key of Object.keys(value))
        if (!known.has(key))
          errors.push({ type: "extra_forbidden", loc: [...loc, key], msg: "Extra inputs are not permitted", input: value[key] });
      if (errors.length > before) return INVALID;
      try {
        uniqueLists(result, type);
        for (const validate of type.validators) validate(result);
      } catch (e) {
        return add("value_error", "Value error, " + e.message);
      }
      return result;
    }
  }
  throw new Error("unknown field type");
}

// ----- Plain-language errors linked to form fields (webapp/validation.py) --------------
function friendlyMessage(error) {
  const kind = error.type;
  if (kind === "missing" || kind === "string_too_short" || (kind === "string_type" && error.input === null))
    return "This answer is required.";
  if (kind === "string_pattern_mismatch")
    return String(error.ctx?.pattern || "").includes("[0-9]{4}")
      ? "Use the format DD-MM-YYYY, for example 23-04-1990."
      : "This answer is not in the expected format.";
  if (kind === "bool_type" || kind === "bool_parsing") return "Choose Yes or No.";
  if (kind === "too_short") return "Choose or enter at least one item.";
  if (kind === "literal_error" || kind === "enum") return "Choose one of the listed options.";
  if (["dict_type", "model_type", "list_type"].includes(kind))
    return "This section is incomplete. Answer its questions or mark it as not applicable.";
  const message = error.msg.replace(/^Value error, /, "");
  return (
    {
      "date must use DD-MM-YYYY": "Use the format DD-MM-YYYY, for example 23-04-1990.",
      "date is not a valid calendar date": "This date does not exist. Check the day and month.",
    }[message] || message
  );
}

function textBounds(value) {
  if (typeof value === "string" && value.length > 4000) throw new Error("An applicant value exceeds 4,000 characters");
  if (value && typeof value === "object") for (const child of Object.values(value)) textBounds(child);
}

/** Validate applicant data: returns {applicant, errors} like validation.validation_errors. */
export function validationErrors(data, meta) {
  try {
    textBounds(data);
  } catch (e) {
    return { applicant: null, errors: [{ path: "", paths: [], message: e.message }] };
  }
  const raw = [];
  const applicant = check(ApplicantModel, data, [], raw);
  if (!raw.length) return { applicant, errors: [] };
  const paths = meta.fields.map((f) => f.path);
  const errors = raw.map((error) => {
    const loc = error.loc;
    const stayIndex = loc.length > 1 && loc[0] === "accommodation" && Number.isInteger(loc[1]) ? loc[1] : null;
    const path = loc.filter((p) => !Number.isInteger(p)).join(".");
    const message = error.msg.replace(/^Value error, /, "");
    let linked = meta.errorLinks.find((link) => message.includes(link.phrase))?.paths || [];
    if (!linked.length) {
      const candidates = paths.filter((p) => p === path || p.startsWith(path + "."));
      const matching = candidates.filter((p) => message.includes(p.split(".").at(-1)));
      linked = matching.length ? matching : candidates.length ? candidates.slice(0, 1) : [path];
    }
    if (stayIndex !== null && stayIndex > 0) linked = linked.map((p) => p.replace("accommodation.", `accommodation.${stayIndex}.`));
    return { path: linked.length ? linked[0] : path, paths: linked, message: friendlyMessage(error) };
  });
  return { applicant: null, errors };
}
