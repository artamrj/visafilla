import { get, hasValue, containsPlaceholder } from "./helpers.js";

export function createRules(meta) {
  function fieldsFor(p) {
    const stays = p?.data?.accommodation;
    const count = Array.isArray(stays) ? stays.length : stays ? 1 : 0;
    return meta.fields.flatMap(f => f.group !== "accommodation" ? [f] :
      Array.from({length: count}, (_, index) => ({...f, stayIndex: index,
        path: index === 0 ? f.path : f.path.replace("accommodation.", `accommodation.${index}.`)})));
  }
  function age(p) {
    const b = get(p.data, "personal.date_of_birth"),
      a = get(p.data, "application.date");
    if (
      !/^\d{2}-\d{2}-\d{4}$/.test(b || "") ||
      !/^\d{2}-\d{2}-\d{4}$/.test(a || "")
    )
      return null;
    const [bd, bm, by] = b.split("-").map(Number),
      [ad, am, ay] = a.split("-").map(Number);
    if (!by || !ay) return null;
    return ay - by - (am < bm || (am === bm && ad < bd) ? 1 : 0);
  }
  function matches(condition, p) {
    if (condition.ageAtLeast !== undefined) {
      const years = age(p);
      return years !== null && years >= condition.ageAtLeast;
    }
    const value = get(p.data, condition.path);
    if (condition.not !== undefined) return value !== condition.not;
    if (condition.notOneOf) return !condition.notOneOf.includes(value);
    if (condition.oneOf) return condition.oneOf.includes(value);
    return Array.isArray(value) ? value.includes(condition.equals) : value === condition.equals;
  }
  function groupAvailable(g, p) {
    return !(meta.rules.unavailable[g.path] || []).some(c => matches(c, p));
  }
  function groupEnabled(g, p) {
    return groupAvailable(g, p) && (!g.optional || get(p.data, g.path) != null);
  }
  function active(f, p) {
    const g = meta.groups.find(g => g.path === f.group);
    const path = f.path.replace(/^accommodation\.\d+\./, "accommodation.");
    return groupEnabled(g, p) && (meta.rules.visible[path] || []).every(c => matches(c, p));
  }
  function required(f) {
    const path = f.path.replace(/^accommodation\.\d+\./, "accommodation.");
    return f.required || meta.rules.required.includes(path);
  }
  function progress(p, step = null) {
    const fields = fieldsFor(p).filter(
      (f) => (step === null || f.step === step) && active(f, p) && required(f, p),
    );
    const groups = meta.groups.filter(
      (g) =>
        g.optional && groupAvailable(g, p) && (step === null || g.step === step),
    );
    let done =
      fields.filter((f) => hasValue(get(p.data, f.path))).length +
      groups.filter((g) => typeof p.sectionAnswers[g.path] === "boolean").length;
    const total = fields.length + groups.length;
    return {
      done,
      total,
      percent: total ? Math.round((done / total) * 100) : 100,
    };
  }
  // Only answers the user did not enter themselves (imported, suggested or example values) need a check.
  const REVIEW_SOURCES = ["imported", "assumed", "supplied", "fictional"];
  function needsCheck(p, path) {
    // The sample applicant is fictional on purpose; its PDF is still named as a draft.
    if (p.sample) return false;
    const v = get(p.data, path);
    if (!hasValue(v)) return false;
    return containsPlaceholder(v) || (REVIEW_SOURCES.includes(p.marks[path]) && !p.confirmed[path]);
  }
  function needsReview(p) {
    return fieldsFor(p).filter((f) => active(f, p) && needsCheck(p, f.path));
  }
  function isDraft(p, unreviewed = needsReview(p).length) {
    return (
      get(p.data, "previous_biometrics.fingerprints_taken") == null ||
      unreviewed > 0 ||
      containsPlaceholder(p.data)
    );
  }

  function clearPlan(candidate) {
    const d = candidate.data,
      clear = [];
    const add = (path, value = null) => {
      if (hasValue(get(d, path))) clear.push({ path, value });
    };
    for (const rule of meta.rules.clear) {
      if (matches(rule.when, candidate))
        for (const path of rule.paths) add(path);
    }
    for (const f of fieldsFor(candidate)) {
      if (
        !active(f, candidate) &&
        hasValue(get(d, f.path)) &&
        !clear.some((c) => f.path.startsWith(c.path + "."))
      ) {
        add(f.path, f.kind === "multi" || f.kind === "list" ? [] : null);
      }
    }
    return clear.filter(
      (c, i, all) =>
        !all.some((other, j) => i !== j && c.path.startsWith(other.path + ".")),
    );
  }

  return { fieldsFor, age, groupAvailable, groupEnabled, active, required, progress, needsCheck, needsReview, isDraft, clearPlan };
}
