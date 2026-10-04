// Strict JSON for applicant files, matching webapp/validation.py parse_object:
// duplicate keys, non-object roots, deep nesting and oversized values are rejected.

export const MAX_TEXT = 3_000_000;

class Parser {
  constructor(text) {
    this.text = text;
    this.i = 0;
  }
  fail(message) {
    const before = this.text.slice(0, this.i).split("\n");
    throw new Error(`Invalid JSON at line ${before.length}, column ${before.at(-1).length + 1}: ${message}`);
  }
  space() {
    while (/[ \t\n\r]/.test(this.text[this.i] || "")) this.i++;
  }
  expect(char) {
    if (this.text[this.i] !== char) this.fail(`Expecting '${char}'`);
    this.i++;
  }
  value() {
    this.space();
    const c = this.text[this.i];
    if (c === "{") return this.object();
    if (c === "[") return this.array();
    if (c === '"') return this.string();
    if (c === "-" || /[0-9]/.test(c || "")) return this.number();
    for (const [word, value] of [["true", true], ["false", false], ["null", null]]) {
      if (this.text.startsWith(word, this.i)) {
        this.i += word.length;
        return value;
      }
    }
    if (/^(NaN|-?Infinity)/.test(this.text.slice(this.i))) throw new Error("JSON cannot contain non-finite numbers");
    this.fail("Expecting value");
  }
  object() {
    this.i++;
    const result = {};
    const seen = new Set();
    this.space();
    if (this.text[this.i] === "}") {
      this.i++;
      return result;
    }
    for (;;) {
      this.space();
      if (this.text[this.i] !== '"') this.fail("Expecting property name enclosed in double quotes");
      const key = this.string();
      if (seen.has(key)) throw new Error(`duplicate JSON key: ${key}`);
      seen.add(key);
      this.space();
      this.expect(":");
      Object.defineProperty(result, key, { value: this.value(), enumerable: true, writable: true, configurable: true });
      this.space();
      if (this.text[this.i] === ",") {
        this.i++;
        continue;
      }
      this.expect("}");
      return result;
    }
  }
  array() {
    this.i++;
    const result = [];
    this.space();
    if (this.text[this.i] === "]") {
      this.i++;
      return result;
    }
    for (;;) {
      result.push(this.value());
      this.space();
      if (this.text[this.i] === ",") {
        this.i++;
        continue;
      }
      this.expect("]");
      return result;
    }
  }
  string() {
    const start = this.i;
    this.i++;
    for (;;) {
      const c = this.text[this.i];
      if (c === undefined) this.fail("Unterminated string starting at");
      if (c === '"') break;
      if (c === "\\") this.i++;
      else if (c < " ") this.fail("Invalid control character at");
      this.i++;
    }
    this.i++;
    try {
      return JSON.parse(this.text.slice(start, this.i));
    } catch {
      this.i = start;
      return this.fail("Invalid \\escape");
    }
  }
  number() {
    const match = /^-?(0|[1-9]\d*)(\.\d+)?([eE][+-]?\d+)?/.exec(this.text.slice(this.i));
    if (!match) this.fail("Expecting value");
    this.i += match[0].length;
    const value = Number(match[0]);
    if (!Number.isFinite(value)) throw new Error("JSON cannot contain non-finite numbers");
    return value;
  }
}

function bounds(value, depth = 0) {
  if (depth > 12) throw new Error("JSON nesting is too deep");
  if (typeof value === "string" && value.length > MAX_TEXT) throw new Error("JSON text is too long");
  if (Array.isArray(value)) {
    if (value.length > 100) throw new Error("Too many list items");
    for (const child of value) bounds(child, depth + 1);
  } else if (value && typeof value === "object") {
    if (Object.keys(value).length > 150) throw new Error("Too many JSON properties");
    for (const child of Object.values(value)) bounds(child, depth + 1);
  }
}

export function parseObject(text) {
  const parser = new Parser(String(text));
  const value = parser.value();
  parser.space();
  if (parser.i < parser.text.length) parser.fail("Extra data");
  if (!value || typeof value !== "object" || Array.isArray(value)) throw new Error("JSON must contain an applicant object");
  bounds(value);
  return value;
}
