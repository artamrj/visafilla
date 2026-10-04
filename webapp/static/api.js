import { syncJSON } from "./helpers.js";

export function createAPI(meta) {
  async function api(route, body) {
    const res = await fetch(route, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-App-Token": meta.token },
      body: JSON.stringify(body),
    });
    const data = await res.json();
    return { ok: res.ok, ...data };
  }
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
