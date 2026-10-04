// The whole application backend, running in the browser: applicant data never leaves the device.
// It answers the same requests the UI used to send to a server: parse, validate and generate.

import { parseObject } from "./json.js";
import { validationErrors } from "./schema.js";
import { prepare, paint } from "./fill.js";

const PLACEHOLDER = /FICTIONAL|DEMO-|\.example/i;

function base64Bytes(text) {
  const binary = atob(text);
  return Uint8Array.from(binary, (c) => c.charCodeAt(0));
}

async function sha256(bytes) {
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  return [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

/** Errors for one applicant: schema problems first, then anything that cannot be printed. */
export async function checkApplicant(data, meta, signature = null) {
  const { applicant, errors } = validationErrors(data, meta);
  if (errors.length) return { errors };
  try {
    return { applicant, prepared: await prepare(applicant, meta.layout, signature), errors: [] };
  } catch (e) {
    const message = e.message;
    let path = message.split(":")[0];
    const known = meta.fields.map((f) => f.path);
    if (!known.includes(path)) path = known.find((p) => p.startsWith(path + ".")) || "";
    return { errors: [{ path, paths: path ? [path] : [], message }] };
  }
}

export function createEngine(meta) {
  let template = null;
  let previous = [];

  async function templateBytes() {
    if (!template) {
      const { url, sha256: expected } = meta.layout.template;
      const response = await fetch(url);
      if (!response.ok) throw new Error("The official form could not be loaded. Check your connection and reload.");
      const bytes = new Uint8Array(await response.arrayBuffer());
      if ((await sha256(bytes)) !== expected) throw new Error("The official form file is not the expected version.");
      template = bytes;
    }
    return template;
  }

  async function previews(pdf) {
    const pdfjs = await import("../vendor/pdf.min.mjs");
    pdfjs.GlobalWorkerOptions.workerSrc = new URL("../vendor/pdf.worker.min.mjs", import.meta.url).href;
    const task = pdfjs.getDocument({ data: pdf.slice() });
    const doc = await task.promise;
    const pages = [];
    for (let n = 1; n <= doc.numPages; n++) {
      const page = await doc.getPage(n);
      const viewport = page.getViewport({ scale: 120 / 72 });
      const canvas = document.createElement("canvas");
      canvas.width = Math.ceil(viewport.width);
      canvas.height = Math.ceil(viewport.height);
      await page.render({ canvas, canvasContext: canvas.getContext("2d"), viewport }).promise;
      const blob = await new Promise((resolve) => canvas.toBlob(resolve, "image/png"));
      pages.push(URL.createObjectURL(blob));
    }
    await task.destroy();
    return pages;
  }

  async function generate(body, checked) {
    const pdf = await paint(await templateBytes(), meta.layout, checked.prepared);
    for (const url of previous) URL.revokeObjectURL(url);
    const pdfUrl = URL.createObjectURL(new Blob([pdf], { type: "application/pdf" }));
    const pages = await previews(pdf);
    previous = [pdfUrl, ...pages];
    const name = String(body.name || "applicant").replace(/[^A-Za-z0-9_-]+/g, "_").slice(0, 70).replace(/^[_-]+|[_-]+$/g, "") || "applicant";
    const draft =
      checked.applicant.previous_biometrics.fingerprints_taken === null ||
      body.draft !== false ||
      PLACEHOLDER.test(JSON.stringify(body.data));
    return {
      pdf: pdfUrl,
      pages,
      filename: `${name}_schengen_application${draft ? "_draft" : ""}.pdf`,
      revision: String(body.revision ?? "").slice(0, 100),
      draft,
    };
  }

  /** Same contract as the former server API: resolves to {ok, ...result}. */
  async function api(route, body) {
    try {
      if (route === "/api/parse") {
        const data = parseObject(body.text ?? "");
        if (data.accommodation && typeof data.accommodation === "object" && !Array.isArray(data.accommodation))
          data.accommodation = [data.accommodation];
        return { ok: true, data, errors: validationErrors(data, meta).errors };
      }
      const data = body.data;
      if (!data || typeof data !== "object" || Array.isArray(data)) throw new Error("Applicant data must be an object");
      const signature = body.signature ? base64Bytes(body.signature) : null;
      if (signature && signature.length > 1_500_000) throw new Error("Signature image must be smaller than 1.5 MB");
      const checked = await checkApplicant(data, meta, signature);
      if (checked.errors.length) return { ok: false, errors: checked.errors };
      if (route === "/api/validate") return { ok: true, valid: true };
      return { ok: true, ...(await generate(body, checked)) };
    } catch (e) {
      return { ok: false, error: e.message || "Could not finish this request." };
    }
  }

  return { api };
}
