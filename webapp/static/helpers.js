const $ = (id) => document.getElementById(id);
const clone = (value) => structuredClone(value);
const esc = (value) =>
  String(value ?? "").replace(
    /[&<>"']/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        c
      ],
  );
const human = (value) =>
  String(value ?? "")
    .replaceAll("_", " ")
    .replace(/^\w/, (c) => c.toUpperCase());
function accommodationPath(obj, path) {
  if (Array.isArray(obj.accommodation) && /^accommodation\.[^0-9]/.test(path))
    return path.replace("accommodation.", "accommodation.0.");
  return path;
}
const get = (obj, path) => accommodationPath(obj, path).split(".")
  .reduce((v, k) => v && typeof v === "object" ? v[k] : undefined, obj);
function set(obj, path, value) {
  const keys = accommodationPath(obj, path).split(".");
  let node = obj;
  for (let i = 0; i < keys.length - 1; i++) {
    const k = keys[i];
    if (!node[k] || typeof node[k] !== "object")
      node[k] = /^\d+$/.test(keys[i + 1]) ? [] : {};
    node = node[k];
  }
  node[keys.at(-1)] = value;
}
function normalizeAccommodation(data) {
  if (data.accommodation && !Array.isArray(data.accommodation))
    data.accommodation = [data.accommodation];
  return data;
}
const hasValue = (v) =>
  v !== null &&
  v !== undefined &&
  v !== "" &&
  (!Array.isArray(v) || v.length > 0);
const valueText = (v) =>
  Array.isArray(v)
    ? v.map(human).join(", ")
    : typeof v === "boolean"
      ? v
        ? "Yes"
        : "No"
      : (v ?? "Not provided");
const placeholder = (v) =>
  typeof v === "string" && /FICTIONAL|DEMO-|\.example/i.test(v);


function containsPlaceholder(value) {
  if (typeof value === "string") return placeholder(value);
  if (value && typeof value === "object") return Object.values(value).some(containsPlaceholder);
  return false;
}
function markEdited(p, path) {
  p.marks[path] = "entered";
  p.confirmed[path] = false;
}
// Quick format checks run when a field is finished; the server still validates everything.
function localError(f, v) {
  if (typeof v !== "string") return null;
  if (f.kind === "date") {
    const m = /^(\d{2})-(\d{2})-(\d{4})$/.exec(v);
    if (!m) return "Use the format DD-MM-YYYY, for example 23-04-1990.";
    const [d, mo, y] = [Number(m[1]), Number(m[2]), Number(m[3])];
    const date = new Date(Date.UTC(y, mo - 1, d));
    if (date.getUTCFullYear() !== y || date.getUTCMonth() !== mo - 1 || date.getUTCDate() !== d)
      return "This date does not exist. Check the day and month.";
  }
  if (/(^|\.)email$/.test(f.path) && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(v))
    return "Enter a valid email address, for example name@example.com.";
  return null;
}
function syncJSON(p) {
  if (!p.jsonDirty) p.jsonText = JSON.stringify(p.data, null, 2);
}

export { $, clone, esc, human, get, set, normalizeAccommodation, hasValue, valueText, placeholder, containsPlaceholder, markEdited, localError, syncJSON };
