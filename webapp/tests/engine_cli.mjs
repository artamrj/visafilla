// Runs the in-browser engine under Node for the parity tests.
// Input on stdin: a JSON list of {data, signature?, render?} or {text}; output: one result per case.
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { checkApplicant } from "../static/engine/index.js";
import { parseObject } from "../static/engine/json.js";
import { paint, valuesAndChecks } from "../static/engine/fill.js";

const meta = JSON.parse(readFileSync(fileURLToPath(new URL("../static/meta.json", import.meta.url)), "utf8"));
const cases = JSON.parse(readFileSync(0, "utf8"));
const results = [];
for (const item of cases) {
  if ("text" in item) {
    try {
      parseObject(item.text);
      results.push({ parsed: true });
    } catch (e) {
      results.push({ parsed: false, error: e.message });
    }
    continue;
  }
  const signature = item.signature ? Uint8Array.from(Buffer.from(item.signature, "base64")) : null;
  const checked = await checkApplicant(item.data, meta, signature);
  if (checked.errors.length) {
    results.push({ errors: checked.errors });
    continue;
  }
  if (item.render) {
    const template = readFileSync(fileURLToPath(new URL("../static/" + meta.layout.template.url, import.meta.url)));
    const pdf = await paint(new Uint8Array(template), meta.layout, checked.prepared);
    results.push({ errors: [], pdf: Buffer.from(pdf).toString("base64") });
    continue;
  }
  const { values, checks } = valuesAndChecks(checked.applicant, meta.layout);
  results.push({
    errors: [],
    values,
    checks,
    placements: checked.prepared.placements.map((p) => ({ key: p.key, lines: p.lines, size: p.size })),
  });
}
process.stdout.write(JSON.stringify(results));
