// Fill the official PDF in the browser: a port of script/core/renderer.py using pdf-lib.
// Text is measured with standard Helvetica widths, the same metrics PyMuPDF uses, so wrapping
// and shrinking match the Python engine. Parity tests compare both on every scenario.

import { PDFDocument, StandardFonts, rgb } from "../vendor/pdf-lib.esm.min.js";

// PyMuPDF's built-in Helvetica line metrics (fitz.Font("helv").ascender / .descender).
const ASCENDER = 1.0750000476837158;
const DESCENDER = -0.29899999499320984;

/** Translate applicant data into measured field values and checkbox keys. */
export function valuesAndChecks(a, layout) {
  let values = {};
  const checks = [];
  const flatten = (prefix, obj) => {
    if (obj && typeof obj === "object" && !Array.isArray(obj)) {
      for (const [key, value] of Object.entries(obj)) flatten(prefix ? `${prefix}.${key}` : key, value);
    } else if (prefix in layout.fields && obj !== null && obj !== undefined) {
      values[prefix] = Array.isArray(obj) ? obj.join(", ") : String(obj);
    }
  };
  flatten("", a);
  const p = a.personal;
  // Nationality at birth is requested only if different; the data itself is unchanged.
  if (p.nationality_at_birth && p.nationality_at_birth.toLowerCase() === p.current_nationality.toLowerCase())
    delete values["personal.nationality_at_birth"];
  checks.push(
    `sex.${p.sex}`,
    `marital.${p.marital_status}`,
    `passport.${a.passport.type}`,
    `entries.${a.journey.entries_requested}`,
    "residence." + (a.residence.lives_outside_country_of_nationality ? "yes" : "no"),
  );
  if (a.previous_biometrics.fingerprints_taken !== null)
    checks.push("fingerprints." + (a.previous_biometrics.fingerprints_taken ? "yes" : "no"));
  checks.push(...a.journey.purposes.map((purpose) => "purpose." + purpose));
  if (a.guardian) {
    const g = a.guardian;
    values.guardian = [`${g.surname} ${g.given_names}; ${g.nationality}`, g.address, `${g.phone}; ${g.email}`]
      .filter(Boolean)
      .join("\n");
  }
  if (a.eu_family_member) checks.push("relationship." + a.eu_family_member.relationship);
  if (a.occupation && a.occupation.employer_or_school) {
    const e = a.occupation.employer_or_school;
    values["occupation.employer_or_school"] = [e.name, e.address, e.phone].filter(Boolean).join("; ");
  }
  if (a.inviting_company) {
    const c = a.inviting_company;
    values["inviting_company.name_address"] = `${c.name}; ${c.address}`;
    values["inviting_company.contact"] = `${c.contact.surname} ${c.contact.given_names}\n${c.contact.address}\n${c.contact.email}`;
  }
  if (a.expenses) {
    const e = a.expenses;
    if (e.applicant_means.length) checks.push("payer.applicant", ...e.applicant_means.map((m) => "applicant." + m));
    if (e.sponsor_means.length) checks.push("payer.sponsor", ...e.sponsor_means.map((m) => "sponsor." + m));
    if (e.sponsor) checks.push("sponsor_reference." + (e.sponsor.reference === "other" ? "other" : "form"));
  }
  const notes = [a.journey.additional_information];
  const stays = a.accommodation || [];
  if (stays.length) {
    const labelled = (stay, text) => (stay.city ? `${stay.city}: ${text}` : text);
    const withBooking = (stay) => {
      let name = labelled(stay, stay.name);
      const booking = [];
      if (stay.check_in && stay.check_out) booking.push(`${stay.check_in} to ${stay.check_out}`);
      if (stay.confirmation_code) booking.push(stay.confirmation_code);
      if (booking.length) name = `${name}: ${booking.join("; ")}`;
      return name;
    };
    values["accommodation.name"] = stays.map(withBooking).join("\n");
    values["accommodation.address"] = stays
      .map((stay) => {
        const endsWithCountry =
          !stay.country || stay.address.replace(/[ .]+$/, "").toLowerCase().endsWith(stay.country.toLowerCase());
        const address = endsWithCountry ? stay.address : `${stay.address}, ${stay.country}`;
        return labelled(stay, address + (stay.email ? `; ${stay.email}` : ""));
      })
      .join("\n");
    values["accommodation.phone"] = stays.map((stay) => labelled(stay, stay.phone)).join("\n");
    notes.push(...stays.filter((stay) => stay.booking_details).map((stay) => stay.booking_details));
  }
  if (notes.some(Boolean)) values["journey.additional_information"] = notes.filter(Boolean).join("; ");
  values["application.place_date"] = `${a.application.place}\n${a.application.date}`;
  // Upper-case everything except email addresses, which keep their spelling.
  for (const [key, value] of Object.entries(values)) {
    if (key.endsWith(".email")) continue;
    values[key] = value
      .split(/([^\s;]+@[^\s;]+)/)
      .map((part) => (part.includes("@") ? part : part.toUpperCase()))
      .join("");
  }
  values = Object.fromEntries(Object.entries(values).filter(([, v]) => v));
  return { values, checks };
}

// Scripts that need shaping or right-to-left layout cannot be printed correctly here.
const SHAPED = /[\p{Script=Arabic}\p{Script=Hebrew}\p{Script=Syriac}\p{Script=Thaana}\p{Script=Nko}\p{M}]/u;
const SUPPORTED_LETTERS = /[\p{Script=Latin}\p{Script=Greek}\p{Script=Cyrillic}\p{Script=Han}\p{Script=Hiragana}\p{Script=Katakana}\p{Script=Hangul}]/u;

function wrap(text, width, measure, size, multiline) {
  if (!multiline) return [text.replaceAll("\n", " ")];
  const lines = [];
  for (const paragraph of text.split("\n")) {
    let line = "";
    for (let word of paragraph.split(/\s+/).filter(Boolean)) {
      const candidate = `${line} ${word}`.trim();
      if (measure(candidate, size) <= width) {
        line = candidate;
        continue;
      }
      if (line) {
        lines.push(line);
        line = "";
      }
      while (measure(word, size) > width) {
        let n = 1;
        while (n < word.length && measure(word.slice(0, n + 1), size) <= width) n++;
        if (measure(word.slice(0, n), size) > width) return [text]; // not even one glyph fits
        lines.push(word.slice(0, n));
        word = word.slice(n);
      }
      line = word;
    }
    lines.push(line);
  }
  return lines;
}

// Width without kerning: PyMuPDF measures plain advance widths and neither engine kerns when
// drawing, while pdf-lib's widthOfTextAtSize would subtract kerning pairs such as "AV".
const advances = new WeakMap();
export function textWidth(font, text, size) {
  if (!advances.has(font)) advances.set(font, new Map());
  const cache = advances.get(font);
  let units = 0;
  for (const c of text) {
    if (!cache.has(c)) cache.set(c, font.widthOfTextAtSize(c, 1000));
    units += cache.get(c);
  }
  return (units / 1000) * size;
}

/** Find a legible size for one value; never truncate or substitute text. */
export function fitText(key, text, field, font) {
  for (const c of text) {
    if (c === "\n") continue;
    if (SHAPED.test(c))
      throw new Error(`${key}: script requires shaping not supported by this renderer; supply the passport Latin spelling`);
    if (/\p{L}/u.test(c) && !SUPPORTED_LETTERS.test(c))
      throw new Error(`${key}: unsupported script shaping; supply a reliable Latin spelling`);
    try {
      font.encodeText(c);
    } catch {
      const code = c.codePointAt(0).toString(16).toUpperCase().padStart(4, "0");
      throw new Error(`${key}: unsupported character U+${code}; supply the passport Latin spelling`);
    }
  }
  const measure = (s, size) => textWidth(font, s, size);
  const [x0, y0, x1, y1] = field.rect;
  const width = x1 - x0,
    height = y1 - y0;
  let size = field.font_size;
  while (size >= field.min_font_size) {
    const lines = wrap(text, width, measure, size, field.multiline);
    const lineHeight = (field.line_spacing || ASCENDER - DESCENDER) * size;
    const total = (ASCENDER - DESCENDER) * size + (lines.length - 1) * lineHeight;
    if (total <= height && lines.every((s) => measure(s, size) <= width)) return { key, field, lines, size };
    size = Math.round((size - 0.25) * 100) / 100;
  }
  throw new Error(
    `${key}: text cannot fit within the measured field at ${field.min_font_size} pt; shorten the value without omitting required information`,
  );
}

function imageKind(bytes) {
  if (!bytes) return null;
  const head = [...bytes.slice(0, 8)];
  if (head.join() === "137,80,78,71,13,10,26,10") return "png";
  if (head[0] === 0xff && head[1] === 0xd8 && head[2] === 0xff) return "jpg";
  return null;
}

/** Validate text fit and the signature before anything is drawn (renderer.prepare). */
export async function prepare(applicant, layout, signature = null) {
  const doc = await PDFDocument.create();
  const font = await doc.embedFont(StandardFonts.Helvetica);
  const { values, checks } = valuesAndChecks(applicant, layout);
  const placements = Object.entries(values).map(([key, value]) => fitText(key, value, layout.fields[key], font));
  for (const key of checks) if (!(key in layout.checkboxes)) throw new Error(`checkbox mapping missing: ${key}`);
  const enabled = applicant.application.signature.enabled;
  if (signature && !enabled)
    throw new Error("application.signature.enabled: enable the signature before attaching an image");
  if (enabled) {
    if (!signature) throw new Error("application.signature.image_path: reattach the signature using the local image picker");
    if (!imageKind(signature)) throw new Error("application.signature.image_path: signature must be PNG or JPEG");
  }
  return { placements, checks, signature: enabled ? signature : null };
}

/** Draw the prepared answers onto the unmodified template and return the PDF bytes. */
export async function paint(templateBytes, layout, prepared) {
  const doc = await PDFDocument.load(templateBytes);
  const font = await doc.embedFont(StandardFonts.Helvetica);
  const pages = doc.getPages();
  const black = rgb(0, 0, 0);
  for (const p of prepared.placements) {
    const page = pages[p.field.page];
    const top = page.getHeight();
    const [x0, y0, x1] = p.field.rect;
    let baseline = y0 + ASCENDER * p.size;
    for (const line of p.lines) {
      let x = x0;
      const width = textWidth(font, line, p.size);
      if (p.field.alignment === "center") x += (x1 - x0 - width) / 2;
      else if (p.field.alignment === "right") x = x1 - width;
      page.drawText(line, { x, y: top - baseline, size: p.size, font, color: black });
      baseline += (p.field.line_spacing || ASCENDER - DESCENDER) * p.size;
    }
  }
  for (const key of prepared.checks) {
    const field = layout.checkboxes[key];
    const page = pages[field.page];
    const top = page.getHeight();
    const [x0, y0, x1, y1] = field.rect.map((v, i) => v + (i < 2 ? 0.65 : -0.65));
    const line = (a, b) => page.drawLine({ start: a, end: b, thickness: 0.55, color: black });
    line({ x: x0, y: top - y0 }, { x: x1, y: top - y1 });
    line({ x: x0, y: top - y1 }, { x: x1, y: top - y0 });
  }
  if (prepared.signature) {
    const image =
      imageKind(prepared.signature) === "png" ? await doc.embedPng(prepared.signature) : await doc.embedJpg(prepared.signature);
    const { page: index, rect } = layout.signature;
    const page = pages[index];
    const [x0, y0, x1, y1] = rect;
    const scale = Math.min((x1 - x0) / image.width, (y1 - y0) / image.height);
    const w = image.width * scale,
      h = image.height * scale;
    page.drawImage(image, { x: x0 + (x1 - x0 - w) / 2, y: page.getHeight() - (y0 + (y1 - y0 + h) / 2), width: w, height: h });
  }
  return doc.save();
}
