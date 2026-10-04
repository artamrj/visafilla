import { syncJSON } from "./helpers.js";
import { createEngine } from "./engine/index.js";

export function createAPI(meta) {
  // Parsing, validation and PDF generation all run in this browser tab.
  const { api } = createEngine(meta);
  function downloadJSON(p, raw = false) {
    syncJSON(p);
    const text = raw ? p.jsonText : JSON.stringify(p.data, null, 2);
    const url = URL.createObjectURL(
      new Blob([text + "\n"], { type: "application/json" }),
    );
    const a = document.createElement("a");
    a.href = url;
    a.download =
      (p.name.replace(/[^A-Za-z0-9_-]+/g, "_") || "applicant") +
      (raw && p.jsonDirty ? "_unapplied" : "") +
      ".json";
    a.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  return { api, downloadJSON };
}
