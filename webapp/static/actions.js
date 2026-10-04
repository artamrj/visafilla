import { $, clone, esc, human, get, set, hasValue, placeholder, syncJSON, markEdited } from "./helpers.js";

export function createActions({context, workspace, rules, storage, ui, requests, refreshAfterEdit, change}) {
  const {meta} = context;
  const {current, session} = workspace;
  const {fieldsFor, clearPlan, isDraft} = rules;
  const {scheduleSave} = storage;
  const {dialog, notify, render, renderReview} = ui;
  const {api} = requests;
  async function pendingJSON(p) {
    if (!p?.jsonDirty) return true;
    const r = await dialog(
      "Keep your JSON edits?",
      '<p>The JSON editor has unapplied edits. They are saved separately from the guided form.</p><p class="hint" lang="fa" dir="rtl">می‌توانید متن را نگه دارید و به فرم بروید؛ تولید PDF از پاسخ‌های فرم انجام می‌شود تا زمانی که JSON را اعمال کنید.</p>',
      [
        { value: "cancel", label: "Stay here" },
        { value: "keep", label: "Keep edits & continue", kind: "primary" },
      ],
    );
    return r.value === "keep";
  }
  async function navigate(step) {
    const p = current();
    if (!p) return;
    if (p.view === "json" && !(await pendingJSON(p))) return;
    p.step = step;
    p.view = "form";
    scheduleSave();
    render();
    $("workspace").focus({ preventScroll: true });
    window.scrollTo({ top: 0, behavior: "instant" });
  }
  async function commitChange(path, value, group = false) {
    const p = current();
    if (!p) return;
    const candidate = clone(p);
    if (group) {
      candidate.sectionAnswers[path] = value;
      set(
        candidate.data,
        path,
        value === true ? get(candidate.data, path) || (path === "accommodation" ? [{}] : {}) : null,
      );
    } else set(candidate.data, path, value);
    if (path === "eu_family_exemption" && value === true) {
      candidate.sectionAnswers.eu_family_member = true;
      if (!candidate.data.eu_family_member) candidate.data.eu_family_member = {};
    }
    if (path === "eu_family_exemption" && value !== true) {
      if (!candidate.data.occupation) candidate.data.occupation = {};
      if (!candidate.data.expenses)
        candidate.data.expenses = { applicant_means: [], sponsor_means: [] };
    }
    let clears = clearPlan(candidate);
    if (group && value !== true && hasValue(get(p.data, path)))
      clears.unshift({ path, value: null });
    if (clears.length) {
      const r = await dialog(
        "Update dependent answers?",
        `<p>This change makes the following details no longer applicable. Continuing will clear them:</p><ul>${clears.map((c) => `<li>${esc(fieldsFor(candidate).find((f) => f.path === c.path)?.label || human(c.path.replaceAll(".", " / ")))}</li>`).join("")}</ul><p class="hint" lang="fa" dir="rtl">پاسخ‌های وابسته فقط با تأیید شما پاک می‌شوند. اگر می‌خواهید آن‌ها را نگه دارید Cancel را بزنید.</p>`,
        [
          { value: "cancel", label: "Cancel" },
          { value: "clear", label: "Clear & continue", kind: "primary" },
        ],
      );
      if (r.value !== "clear") {
        syncJSON(p);
        scheduleSave();
        render();
        return;
      }
    }
    for (const c of clears) {
      set(candidate.data, c.path, c.value);
      if (meta.groups.some((g) => g.optional && g.path === c.path))
        candidate.sectionAnswers[c.path] = false;
      for (const k of Object.keys(candidate.confirmed))
        if (k === c.path || k.startsWith(c.path + "."))
          delete candidate.confirmed[k];
    }
    markEdited(candidate, path);
    if (path === "application.signature.enabled" && value !== true)
      candidate.signature = null;
    Object.assign(p, candidate);
    session(p).errors = [];
    refreshAfterEdit(p);
    document
      .getElementById((group ? "group-" : "field-") + path)
      ?.focus({ preventScroll: true });
  }
  function confirmField(p, path) {
    const v = get(p.data, path);
    if (
      placeholder(v) ||
      (p.marks[path] === "fictional" &&
        JSON.stringify(v) === JSON.stringify(get(p.original, path)))
    ) {
      notify(
        "Replace this fictional value with the real information before confirming it.",
        true,
      );
      return;
    }
    p.confirmed[path] = true;
    scheduleSave();
    render();
  }
  async function runValidation(generate = false) {
    const p = current();
    if (!p || context.busy) return;
    if (p.jsonDirty) {
      const r = await dialog(
        "Apply JSON before generating?",
        "<p>The guided form and JSON editor differ. Apply the JSON first, or explicitly use the current form answers.</p>",
        [
          { value: "cancel", label: "Back to editor" },
          { value: "form", label: "Use form answers", kind: "primary" },
        ],
      );
      if (r.value !== "form") {
        syncJSON(p);
        p.view = "json";
        render();
        return;
      }
    }
    context.busy = true;
    renderReview(p);
    $("next-step").disabled = true;
    $("validate").disabled = true;
    const revision = p.revision;
    try {
      const result = await api(generate ? "/api/generate" : "/api/validate", {
        data: p.data,
        signature: p.signature,
        name: p.name.toLowerCase(),
        draft: isDraft(p),
        revision: String(revision),
      });
      const rt = session(p);
      if (p.revision !== revision) {
        notify(
          "Answers changed during validation. Check the current version again.",
        );
        return;
      }
      if (!result.ok) {
        rt.errors = result.errors || [
          {
            path: "",
            paths: [],
            message: result.error || "Could not finish this request.",
          },
        ];
        rt.validated = null;
        notify(
          "Some details need attention. Select an error to go to its question.",
          true,
        );
      } else {
        rt.errors = [];
        rt.validated = revision;
        if (generate) {
          rt.artifact = result;
          rt.page = 0;
          p.step = 7;
          p.view = "form";
          scheduleSave();
          notify(
            "Your four-page PDF is ready. Review every page before downloading.",
          );
        } else
          notify(
            "Validation passed: the answers are consistent and fit the official form.",
          );
      }
    } catch (e) {
      notify(
        "Something went wrong while preparing the PDF. Your draft is safe; reload the page and try again.",
        true,
      );
    } finally {
      context.busy = false;
      $("validate").disabled = false;
      render();
      // Scroll after the next frame, once the summary has re-rendered above the target.
      const target = generate && session(p).artifact ? "preview-content" : session(p).errors.length ? "errors-panel" : null;
      if (target)
        requestAnimationFrame(() =>
          requestAnimationFrame(() =>
            $(target).scrollIntoView({ behavior: "instant", block: target === "errors-panel" ? "center" : "start" }),
          ),
        );
    }
  }
  async function applyJSON() {
    const p = current();
    if (!p) return;
    try {
      const r = await api("/api/parse", { text: p.jsonText });
      if (!r.ok) {
        $("json-status").textContent =
          r.error || r.errors?.[0]?.message || "Invalid JSON";
        return;
      }
      const data = r.data;
      for (const f of [...fieldsFor(p), ...fieldsFor({data})]) {
        if (
          JSON.stringify(get(p.data, f.path)) !==
          JSON.stringify(get(data, f.path))
        ) {
          p.confirmed[f.path] = false;
          p.marks[f.path] = "imported";
        }
      }
      p.data = data;
      p.jsonDirty = false;
      p.jsonText = JSON.stringify(data, null, 2);
      p.signature = null;
      for (const g of meta.groups.filter((g) => g.optional))
        p.sectionAnswers[g.path] = get(data, g.path) != null;
      session(p).errors = r.errors || [];
      change(p);
      render();
      $("json-status").textContent = r.errors?.length
        ? "JSON applied. Some answers still need validation."
        : "JSON applied to the guided form. Use Check application for layout validation.";
    } catch (e) {
      $("json-status").textContent =
        "Could not apply this JSON. Your edits are preserved.";
    }
  }


  return { pendingJSON, navigate, commitChange, confirmField, runValidation, applyJSON };
}
