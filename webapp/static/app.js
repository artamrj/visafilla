import { $, clone, esc, get, set, normalizeAccommodation, syncJSON, markEdited, localError } from "./helpers.js";
import { createWorkspace } from "./state.js";
import { createStorage } from "./storage.js";
import { createRules } from "./rules.js";
import { createRenderer } from "./render.js";
import { createAPI } from "./api.js";
import { createActions } from "./actions.js";
import { createCountryPicker } from "./country.js";
import { createWelcome } from "./welcome.js";

const context = { meta: {}, state: { version: 1, profiles: [], activeId: null }, busy: false };
const {meta, state} = context;
const workspace = createWorkspace(context);
const {runtime, textBefore, current, session, makeProfile, blankData} = workspace;
const rules = createRules(meta);
const {fieldsFor, clearPlan} = rules;
const storage = createStorage(state);
const {initDB, readState, storageFailure, persist, scheduleSave, cancelSave, setDB, hasPendingSave} = storage;
const ui = createRenderer(context, workspace, rules);
const {notify, dialog, render, updateSummary, renderPreview, renderReview, renderErrors, refreshField} = ui;
const requests = createAPI(meta);
const {api, downloadJSON} = requests;
let summaryFrame = null;
function change(p) {
  p.revision++;
  p.updated = Date.now();
  scheduleSave();
  if (summaryFrame === null) summaryFrame = requestAnimationFrame(() => {
    summaryFrame = null;
    updateSummary();
    renderPreview();
  });
}
function refreshAfterEdit(p) { change(p); render(); }
function saveProfiles() { persist(); render(); }
const actions = createActions({context, workspace, rules, storage, ui, requests, refreshAfterEdit, change});
const {pendingJSON, navigate, commitChange, confirmField, runValidation, applyJSON} = actions;
let db;
// Imported only by browser tests; application state is not a window global.
export const testAdapter = {state, current, makeProfile, render, persist, readState, closeDB: () => db?.close()};
// The sample applicant is only for trying the app: it leaves as soon as a real one arrives.
function dropSamples() {
  for (const q of state.profiles.filter((q) => q.sample)) runtime.delete(q.id);
  state.profiles = state.profiles.filter((q) => !q.sample);
}
function addSample() {
  const existing = state.profiles.find((q) => q.sample);
  if (existing) state.activeId = existing.id;
  else {
    const p = makeProfile("Sample applicant", meta.sample);
    p.sample = true;
    state.profiles.push(p);
    state.activeId = p.id;
  }
  saveProfiles();
}
function newProfile(name) {
  const p = makeProfile(name, blankData());
  p.sectionAnswers = {};
  dropSamples();
  state.profiles.push(p);
  state.activeId = p.id;
  saveProfiles();
}

// Applicant menu: switch, import, manage and clear without growing the sidebar.
const menu = $("applicant-menu"),
  switcher = $("applicant-switch");
function setMenu(open) {
  menu.hidden = !open;
  switcher.setAttribute("aria-expanded", String(open));
  if (open) menu.querySelector(".profile-button.active, .profile-button, .menu-item")?.focus();
}
switcher.onclick = () => setMenu(menu.hidden);
menu.addEventListener("click", (event) => {
  if (event.target.closest("button")) setMenu(false);
});
document.addEventListener("click", (event) => {
  if (!menu.hidden && !event.target.closest("#applicant-menu, #applicant-switch")) setMenu(false);
});
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && !menu.hidden) {
    setMenu(false);
    switcher.focus();
  }
});
$("sample-profile").onclick = addSample;
$("about").onclick = () =>
  dialog(
    "Privacy and disclaimer",
    "<p><strong>Your data stays on this computer.</strong> Answers are saved only in this browser and PDFs are made by the app running on your own machine. Nothing is uploaded. Export a JSON backup to keep your work safe, because clearing browser data deletes drafts.</p><p><strong>Not an official service.</strong> VisaFilla is an independent tool and is not connected to any government, consulate or visa centre. It does not give legal advice. Always check every answer against your documents and the current requirements before signing.</p>",
    [{ value: "ok", label: "Got it", kind: "primary" }],
  );

$("new-profile").onclick = async () => {
  const r = await dialog(
    "Add an applicant",
    '<label for="modal-input">Profile name</label><input id="modal-input" maxlength="60" placeholder="e.g. Alex">',
    [
      { value: "cancel", label: "Cancel" },
      { value: "add", label: "Create applicant", kind: "primary" },
    ],
  );
  if (r.value === "add" && r.input?.trim()) newProfile(r.input.trim());
};
$("import-profile").onclick = () => $("import-file").click();
$("import-file").onchange = async (event) => {
  const file = event.target.files[0];
  event.target.value = "";
  if (!file) return;
  if (file.size > 200000) {
    notify("JSON files must be smaller than 200 KB.", true);
    return;
  }
  try {
    const r = await api("/api/parse", { text: await file.text() });
    if (!r.ok) {
      notify(r.error || r.errors?.[0]?.message || "Invalid JSON", true);
      return;
    }
    const p = makeProfile(
      file.name.replace(/\.json$/i, ""),
      r.data,
      Object.fromEntries(fieldsFor({data: r.data}).map((f) => [f.path, "imported"])),
    );
    dropSamples();
    state.profiles.push(p);
    state.activeId = p.id;
    session(p).errors = r.errors || [];
    saveProfiles();
    notify(
      "Imported as a separate profile. Review the answers and reattach any signature image.",
    );
  } catch (e) {
    notify("Import failed. Check that the local server is running.", true);
  }
};
$("manage-profile").onclick = async () => {
  const p = current();
  if (!p) return;
  const r = await dialog(
    "Manage " + p.name,
    `<label for="modal-input">Profile name</label><input id="modal-input" maxlength="60" value="${esc(p.name)}"><p>Duplicate creates an independent draft and resets all confirmations.</p>`,
    [
      { value: "cancel", label: "Cancel" },
      { value: "delete", label: "Delete", kind: "danger-button" },
      { value: "duplicate", label: "Duplicate" },
      { value: "rename", label: "Save name", kind: "primary" },
    ],
  );
  if (r.value === "rename" && r.input?.trim()) {
    p.name = r.input.trim();
    saveProfiles();
  }
  if (r.value === "duplicate") {
    const q = clone(p);
    q.id = crypto.randomUUID();
    q.name = (r.input?.trim() || p.name) + " copy";
    q.confirmed = {};
    q.signature = null;
    q.marks = Object.fromEntries(fieldsFor(q).map((f) => [f.path, "imported"]));
    q.revision = 0;
    q.sample = false;
    dropSamples();
    state.profiles.push(q);
    state.activeId = q.id;
    saveProfiles();
  }
  if (r.value === "delete") {
    const c = await dialog(
      "Delete this browser draft?",
      `<p>${esc(p.name)} will be removed from this browser. Files you imported or exported are not deleted.</p>`,
      [
        { value: "cancel", label: "Keep draft" },
        { value: "delete", label: "Delete draft", kind: "danger-button" },
      ],
    );
    if (c.value === "delete") {
      state.profiles = state.profiles.filter((q) => q.id !== p.id);
      runtime.delete(p.id);
      state.activeId = state.profiles[0]?.id || null;
      saveProfiles();
    }
  }
};
$("clear-data").onclick = async () => {
  const r = await dialog(
    "Clear all browser drafts?",
    "<p>This clears all applicants, saved JSON edits and attached signatures from this browser. Export JSON backups first. Files saved on your computer stay unchanged.</p>",
    [
      { value: "cancel", label: "Keep drafts" },
      { value: "clear", label: "Clear browser data", kind: "danger-button" },
    ],
  );
  if (r.value === "clear") {
    cancelSave();
    Object.assign(state, { version: 1, profiles: [], activeId: null });
    runtime.clear();
    await persist();
    render();
    notify("Browser drafts cleared. Create a profile or import a JSON backup.");
  }
};
$("form-view").onclick = async () => {
  const p = current();
  if (!p || !(await pendingJSON(p))) return;
  p.view = "form";
  scheduleSave();
  render();
};
$("json-view").onclick = () => {
  const p = current();
  if (!p) return;
  syncJSON(p);
  p.view = "json";
  scheduleSave();
  render();
};
$("json-editor").oninput = () => {
  const p = current();
  if (!p) return;
  p.jsonText = $("json-editor").value;
  p.jsonDirty = true;
  scheduleSave();
  $("json-status").textContent =
    "Unapplied edits saved separately. Apply JSON to update the form.";
};
$("apply-json").onclick = applyJSON;
$("reset-json").onclick = async () => {
  const p = current();
  if (!p) return;
  if (p.jsonDirty) {
    const r = await dialog(
      "Discard unapplied JSON edits?",
      "<p>The editor will be replaced with the current guided-form answers.</p>",
      [
        { value: "cancel", label: "Keep edits" },
        { value: "reset", label: "Use form version", kind: "primary" },
      ],
    );
    if (r.value !== "reset") return;
  }
  p.jsonDirty = false;
  syncJSON(p);
  scheduleSave();
  render();
};
$("download-json").onclick = () => {
  if (current()) downloadJSON(current(), true);
};
$("export-profile").onclick = () => {
  if (current()) downloadJSON(current());
};
$("validate").onclick = () => runValidation();
$("previous-step").onclick = () => {
  if (current()) navigate(Math.max(0, current().step - 1));
};
$("next-step").onclick = () => {
  if (!current()) return;
  if (current().step === 7) runValidation(true);
  else navigate(current().step + 1);
};
document.addEventListener("click", async (event) => {
  const button = event.target.closest("button");
  if (!button) return;
  const p = current();
  if (p && (button.dataset.stayAdd || button.dataset.stayRemove !== undefined)) {
    if (button.dataset.stayAdd) (p.data.accommodation ||= []).push({type: "temporary_accommodation", email: null});
    else p.data.accommodation.splice(Number(button.dataset.stayRemove), 1);
    if (!p.data.accommodation.length) {
      p.data.accommodation = null;
      p.sectionAnswers.accommodation = false;
    }
    for (const key of Object.keys(p.confirmed)) if (key.startsWith("accommodation.")) delete p.confirmed[key];
    refreshAfterEdit(p); return;
  }
  if (button.dataset.profile) {
    state.activeId = button.dataset.profile;
    saveProfiles();
  }
  if (button.dataset.step !== undefined) navigate(Number(button.dataset.step));
  if (button.dataset.confirm && p) confirmField(p, button.dataset.confirm);
  if (button.dataset.error !== undefined && p) {
    const err = session(p).errors[Number(button.dataset.error)],
      f = fieldsFor(p).find(
        (f) => f.path === err.path || f.path.startsWith(err.path + "."),
      );
    if (f) {
      await navigate(f.step);
      const wrapper = document.querySelector(
        `[data-field-wrap="${CSS.escape(f.path)}"]`,
      );
      wrapper?.scrollIntoView({ block: "center", behavior: "instant" });
      const target =
        wrapper?.querySelector("input,select,textarea") ||
        document.getElementById("group-" + f.group);
      target?.scrollIntoView({ block: "center", behavior: "instant" });
      target?.focus({ preventScroll: true });
    }
  }
  if (button.dataset.page !== undefined && p) {
    session(p).page = Number(button.dataset.page);
    renderPreview();
  }
  if (button.id === "generate") runValidation(true);
  if (button.dataset.action === "validate") runValidation();
  if (button.dataset.action === "export" && p) downloadJSON(p);
  if (button.dataset.action === "new") $("new-profile").click();
  if (button.dataset.action === "sample") addSample();
  if (button.dataset.action === "import") $("import-file").click();
});
$("form-content").addEventListener("focusin", (event) => {
  const p = current(),
    path = event.target.dataset.field;
  if (p && path) textBefore.set(p.id + ":" + path, get(p.data, path));
});
$("form-content").addEventListener("input", (event) => {
  const el = event.target,
    path = el.dataset.field,
    p = current();
  if (
    !path ||
    !p ||
    ["SELECT", "FIELDSET"].includes(el.tagName) ||
    ["checkbox", "radio", "file"].includes(el.type)
  )
    return;
  const f = fieldsFor(p).find((f) => f.path === path);
  // Dates: typing digits fills in the dashes, e.g. 23041990 -> 23-04-1990.
  if (f.kind === "date" && !event.inputType?.startsWith("delete")) {
    const digits = el.value.replace(/\D/g, "").slice(0, 8);
    el.value = [digits.slice(0, 2), digits.slice(2, 4), digits.slice(4)].filter(Boolean).join("-");
  }
  set(
    p.data,
    path,
    f.kind === "list"
      ? el.value
          .split(",")
          .map((v) => v.trim())
          .filter(Boolean)
      : el.value || null,
  );
  markEdited(p, path);
  change(p);
  // While typing, drop the old error and status; the field is checked again when it is left.
  const wrap = el.closest(".field");
  wrap?.classList.remove("field-error", "is-ok");
  const note = wrap?.querySelector(".field-note-wrap");
  if (note) note.innerHTML = "";
});
// Remember whether the step guide was closed, so it stays out of the way once read.
$("form-content").addEventListener(
  "toggle",
  (event) => {
    if (!event.target.classList?.contains("step-guide")) return;
    try {
      localStorage.setItem("visafilla.guide", event.target.open ? "open" : "closed");
    } catch {
      // Storage may be blocked; the guide then opens on every step.
    }
  },
  true,
);
// Enter moves to the next question, like a paper form read top to bottom.
$("form-content").addEventListener("keydown", (event) => {
  const el = event.target;
  if (event.key !== "Enter" || el.tagName !== "INPUT" || el.type !== "text" || event.isComposing) return;
  event.preventDefault();
  const fields = [...$("form-content").querySelectorAll("[data-field-wrap]")];
  const next = fields[fields.indexOf(el.closest("[data-field-wrap]")) + 1];
  const target = next?.querySelector("input:checked, input:not([type=file]), textarea") || $("next-step");
  target.focus();
});
$("form-content").addEventListener("change", async (event) => {
  const el = event.target,
    p = current();
  if (!p) return;
  if (el.dataset.group) {
    await commitChange(
      el.dataset.group,
      el.value === "" ? null : el.value === "true",
      true,
    );
    return;
  }
  const path = el.dataset.field;
  if (!path) return;
  const f = fieldsFor(p).find((f) => f.path === path);
  if (f.kind === "file") {
    const file = el.files[0];
    if (!file) return;
    if (
      !["image/png", "image/jpeg"].includes(file.type) ||
      file.size > 1500000
    ) {
      notify("Choose a PNG or JPEG signature smaller than 1.5 MB.", true);
      return;
    }
    const buffer = await file.arrayBuffer();
    let binary = "";
    for (const byte of new Uint8Array(buffer))
      binary += String.fromCharCode(byte);
    p.signature = btoa(binary);
    set(p.data, path, file.name);
    markEdited(p, path);
    refreshAfterEdit(p);
    return;
  }
  if (f.kind === "multi") {
    const values = Array.from(
      $("form-content").querySelectorAll(
        `input[data-field="${CSS.escape(path)}"]:checked`,
      ),
    ).map((e) => e.value);
    await commitChange(path, values);
  } else if (f.kind === "boolean" || f.kind === "select")
    await commitChange(
      path,
      el.value === ""
        ? null
        : f.kind === "boolean"
          ? el.value === "true"
          : el.value,
    );
  else if (
    ["personal.date_of_birth", "application.date"].includes(path) &&
    clearPlan(p).length
  ) {
    const value = get(p.data, path);
    if (textBefore.has(p.id + ":" + path))
      set(p.data, path, textBefore.get(p.id + ":" + path));
    await commitChange(path, value);
  } else {
    // Leaving a typed field finishes it: check it, then confirm a valid real answer.
    const value = get(p.data, path);
    if (typeof value === "string" && !value.trim()) set(p.data, path, null);
    const problem = localError(f, get(p.data, path));
    const rt = session(p);
    rt.errors = rt.errors.filter((e) => !(e.paths || [e.path]).includes(path));
    if (problem) rt.errors.push({ path, paths: [path], message: problem });
    scheduleSave();
    updateSummary();
    renderReview(p);
    renderErrors(p);
    refreshField(p, path);
  }
});
document.addEventListener("visibilitychange", () => {
  if (document.hidden) persist();
});
window.addEventListener("beforeunload", () => {
  if (hasPendingSave()) persist();
});

async function start() {
  try {
    const response = await fetch("/api/bootstrap");
    Object.assign(meta, await response.json());
    if (!response.ok)
      throw new Error(meta.error || "Could not load the local application.");
    try {
      db = setDB(await initDB());
      const saved = await readState();
      if (saved) {
        if (saved.version !== 1 || !Array.isArray(saved.profiles))
          throw new Error(
            "Unsupported saved workspace. Export your drafts before resetting storage.",
          );
        Object.assign(state, saved);
        for (const p of state.profiles) {
          normalizeAccommodation(p.data);
          if (p.original) normalizeAccommodation(p.original);
        }
      } else {
        state.profiles = [];
        state.activeId = null;
        await persist();
      }
    } catch (e) {
      if (db) db.close();
      db = setDB(null);
      storageFailure(e);
      if (!state.profiles.length) {
        state.profiles = [];
        state.activeId = null;
      }
    }
    if (state.profiles.length && !current())
      state.activeId = state.profiles[0].id;
    render();
    if (db) $("save-status").textContent = "Saved on this device";
    // First visit: choose the country, then see how the app works (unless turned off).
    const welcome = createWelcome({ $, onSample: addSample });
    $("help").onclick = welcome.open;
    createCountryPicker({ $, esc, countries: meta.countries || [] }).start(welcome.maybeShow);
  } catch (e) {
    $("fatal").textContent = e.message;
    $("fatal").classList.remove("hidden");
    $("save-status").textContent = "Could not start";
  }
}
start();
