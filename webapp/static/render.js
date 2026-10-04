import { $, esc, human, get, hasValue, valueText, containsPlaceholder } from "./helpers.js";

export function createRenderer(context, workspace, rules) {
  const {meta, state} = context;
  const {current, session} = workspace;
  const {fieldsFor, groupAvailable, groupEnabled, active, required, progress, needsCheck, needsReview, isDraft} = rules;
  function notify(message, error = false) {
    $("message").textContent = message;
    $("message").className = "notice" + (error ? " error" : "");
  }
  // Phones: guides start folded and long summaries collapse, to keep scrolling short.
  const compact = () => window.matchMedia("(max-width: 700px)").matches;
  const icon = (name) => `<svg class="icon" aria-hidden="true"><use href="#i-${name}"/></svg>`;
  const STEP_ICONS = ["user", "passport", "home", "briefcase", "route", "fingerprint", "bed", "file-check"];
  const initial = (p) => esc(p.name[0]?.toUpperCase() || "?");
  function renderProfiles() {
    $("profiles").innerHTML = state.profiles
      .map((p) => {
        const active = p.id === state.activeId;
        return `<button type="button" class="profile-button ${active ? "active" : ""}" data-profile="${esc(p.id)}" ${active ? 'aria-current="true"' : ""}><span class="avatar">${initial(p)}</span><span class="profile-text"><span class="profile-name">${esc(p.name)}${p.sample ? '<span class="sample-badge">Sample</span>' : ""}</span><span class="profile-person">${progress(p).percent}% complete</span></span>${active ? icon("check") : ""}</button>`;
      })
      .join("");
    $("sample-profile").hidden = state.profiles.some((p) => p.sample);
  }
  function renderSteps(p) {
    $("steps").innerHTML = meta.steps
      .map((s, i) => {
        const done = progress(p, i).percent === 100,
          active = i === p.step;
        return `<button type="button" class="step-button ${active ? "active" : ""} ${done ? "done" : ""}" data-step="${i}" aria-label="Step ${i + 1}: ${esc(s.title)}${done ? ", complete" : ""}" ${active ? 'aria-current="step"' : ""}><span class="step-icon">${icon(STEP_ICONS[i] || "file-check")}</span><span class="step-text">${esc(s.title)}</span>${done ? `<span class="step-done">${icon("check")}</span>` : ""}</button>`;
      })
      .join("");
  }
  function updateSummary() {
    const p = current();
    if (!p) return;
    const pr = progress(p),
      unreviewed = needsReview(p).length,
      rt = session(p);
    $("progress-percent").textContent = pr.percent + "%";
    $("completion").value = pr.percent;
    $("progress-detail").textContent =
      `${pr.done}/${pr.total} answered${unreviewed ? ` · ${unreviewed} to check` : ""}`;
    $("completion").textContent = pr.percent + "%";
    $("applicant-avatar").textContent = p.name[0]?.toUpperCase() || "?";
    $("current-name").textContent = p.name;
    $("validation-status").textContent =
      rt.validated === p.revision
        ? "Validation passed"
        : rt.validated === null
          ? "Not validated yet"
          : "Edited since last check";
    $("validation-status").classList.toggle("valid", rt.validated === p.revision);
    renderProfiles();
    renderSteps(p);
  }
  // Persian guidance lives in a tooltip, shown on hover, keyboard focus or tap of the icon.
  // Persian text with embedded Latin words, numbers and dates: isolate each Latin run so
  // values such as 23-04-1990 or +98 912 345 6789 keep their left-to-right order.
  const LATIN_RUN = /([+A-Za-z0-9][A-Za-z0-9+@.,\-\/ ()'’]*[A-Za-z0-9)]|[A-Za-z0-9])/;
  const fa = (text) =>
    text
      .split(LATIN_RUN)
      .map((part, i) => (i % 2 ? `<bdi dir="ltr">${esc(part)}</bdi>` : esc(part)))
      .join("");
  function helpTip(id, text) {
    return text
      ? `<span class="help"><button type="button" class="help-icon" aria-label="Guidance" aria-describedby="${id}" aria-expanded="false">i</button><span class="help-tip" role="tooltip" id="${id}" lang="fa" dir="rtl">${fa(text)}</span></span>`
      : "";
  }
  const OPTION_LABELS = {
    field_30: "The host or accommodation (field 30)",
    field_31: "The inviting company (field 31)",
    single: "Single entry",
    double: "Two entries",
    multiple: "Multiple entries",
    temporary_accommodation: "Rented home / temporary stay",
    inviting_person: "Staying with a host",
    visiting_family_or_friends: "Family or friends",
    airport_transit: "Airport transit",
    applicant: "I pay myself",
    sponsor: "A sponsor pays",
    shared: "Shared",
    ordinary: "Ordinary passport",
  };
  const optionLabel = (o) => OPTION_LABELS[o] || human(o);
  const REVIEW_NOTES = {
    imported: "Imported — check it against your document",
    assumed: "Suggested answer — check it",
    supplied: "Provided — check it against your document",
  };
  // Tap-to-choose chips replace dropdowns: every choice on this form has seven options or fewer.
  function chips(name, attrs, options, isChecked, type = "radio") {
    return options
      .map(
        ([value, label], i) =>
          `<label class="chip"><input class="chip-input" type="${type}" name="${name}" ${attrs(i, value)} value="${esc(String(value))}" ${isChecked(value) ? "checked" : ""}><span>${esc(label)}</span></label>`,
      )
      .join("");
  }
  function fieldMarkup(f, p) {
    const v = get(p.data, f.path),
      id = "field-" + f.path,
      helpId = id + "-help",
      labelId = id + "-label",
      req = required(f, p),
      errors = session(p).errors.filter((e) => (e.paths || [e.path]).includes(f.path)),
      invalid = errors.length ? 'aria-invalid="true"' : "",
      described = `aria-describedby="${helpId}"`,
      choice = ["multi", "boolean", "select"].includes(f.kind);
    let control;
    if (choice) {
      const options =
        f.kind === "boolean" ? [[true, "Yes"], [false, "No"]] : f.options.map((o) => [o, optionLabel(o)]);
      const multi = f.kind === "multi";
      const checkedIndex = options.findIndex(([o]) => (multi ? Array.isArray(v) && v.includes(o) : v === o));
      const attrs = (i) =>
        `id="${(multi ? i === 0 : i === Math.max(checkedIndex, 0)) ? id : `${id}-${i}`}" data-field="${f.path}" ${described} ${invalid}`;
      control = `<div class="chips" role="${multi ? "group" : "radiogroup"}" aria-labelledby="${labelId}">${chips(
        id,
        attrs,
        options,
        (o) => (multi ? Array.isArray(v) && v.includes(o) : v === o),
        multi ? "checkbox" : "radio",
      )}</div>`;
    } else if (f.kind === "file") {
      control = `<input type="file" id="${id}" data-field="${f.path}" ${described} ${invalid} accept="image/png,image/jpeg"><p class="field-caption">${p.signature ? "Attached: " + esc(v) : v ? "Imported path: " + esc(v) + " · attach the image again on this device." : "PNG or JPEG, up to 1.5 MB."}</p>`;
    } else if (f.kind === "textarea") {
      control = `<textarea id="${id}" data-field="${f.path}" ${described} ${invalid} rows="2" spellcheck="false">${esc(typeof v === "string" ? v : "")}</textarea>`;
    } else {
      const text = f.kind === "list" ? (Array.isArray(v) ? v.join(", ") : "") : typeof v === "string" ? v : "";
      const example = f.kind === "date" ? "DD-MM-YYYY" : f.kind === "list" ? "Separate with commas" : "";
      // The right phone keyboard for each answer, and a "Next" key that moves on.
      const keyboard =
        f.kind === "date"
          ? 'inputmode="numeric"'
          : f.path.endsWith(".email")
            ? 'inputmode="email" autocapitalize="off"'
            : f.path.endsWith(".phone")
              ? 'inputmode="tel"'
              : 'autocapitalize="characters"';
      control = `<input type="text" id="${id}" data-field="${f.path}" ${described} ${invalid} value="${esc(text)}" placeholder="${example}" ${keyboard} ${f.kind === "date" ? 'maxlength="10"' : ""} enterkeyhint="next" autocomplete="off" autocorrect="off" spellcheck="false">`;
    }
    const review = needsCheck(p, f.path),
      ok = hasValue(v) && !errors.length && !review,
      tag = req ? "" : f.path.startsWith("previous_biometrics.") ? "If known" : "Optional";
    let note = "";
    if (errors.length)
      note = errors.map((e) => `<p class="field-error-message">${icon("alert")}${esc(e.message)}</p>`).join("");
    else if (review && containsPlaceholder(v))
      note = `<p class="field-note example">${icon("alert")}Example value — replace it with your own</p>`;
    else if (review)
      note = `<p class="field-note review">${esc(REVIEW_NOTES[p.marks[f.path]] || "Check this answer")}<button type="button" class="confirm-button" data-confirm="${f.path}">${icon("check")}Looks right</button></p>`;
    const wide = choice || f.kind === "textarea";
    const label = choice ? `<span class="field-label" id="${labelId}">${esc(f.label)}</span>` : `<label class="field-label" id="${labelId}" for="${id}">${esc(f.label)}</label>`;
    return `<div class="field ${wide ? "wide" : ""} ${errors.length ? "field-error" : ""} ${ok ? "is-ok" : ""}" data-field-wrap="${f.path}"><div class="field-label-row"><span class="label-wrap">${label}${helpTip(helpId, f.hint_fa)}<span class="ok-mark" title="Answered">${icon("check")}</span></span>${tag ? `<span class="requirement">${tag}</span>` : ""}</div>${control}<div class="field-note-wrap">${note}</div></div>`;
  }
  function stepGuide(p) {
    const text = meta.steps[p.step].hint_fa;
    if (!text) return "";
    let open = !compact();
    try {
      const saved = localStorage.getItem("visafilla.guide");
      if (saved) open = saved !== "closed";
    } catch {
      // Storage may be blocked; keep the guide open.
    }
    return `<details class="step-guide" ${open ? "open" : ""}><summary>${icon("info")}<span lang="fa" dir="rtl">راهنمای این مرحله</span>${icon("chevron-down")}</summary><ul lang="fa" dir="rtl">${text
      .split("\n")
      .map((line) => `<li>${fa(line)}</li>`)
      .join("")}</ul></details>`;
  }
  let lastStep = null;
  function renderForm(p) {
    const groups = meta.groups.filter((g) => g.step === p.step);
    const content = $("form-content");
    content.innerHTML =
      (p.sample
        ? `<div class="sample-banner">${icon("sparkle")}<p><strong>You are exploring a sample applicant.</strong> Change anything you like. It is removed as soon as you add your own applicant.</p><button type="button" class="primary" data-action="new">Start my own</button></div>`
        : "") +
      stepGuide(p) +
      groups
        .map((g) => {
          const available = groupAvailable(g, p),
            enabled = groupEnabled(g, p),
            fields = fieldsFor(p).filter((f) => f.group === g.path && active(f, p));
          let inner = "";
          if (!available) {
            inner = `<p class="section-skip">${icon("info")}${g.path === "guardian" ? "Not needed — the applicant is 18 or older on the application date." : "Not needed while the EU-family exemption is used."}</p>`;
          } else {
            if (g.optional) {
              const answer = p.sectionAnswers[g.path];
              const gid = "group-" + g.path;
              inner += `<div class="field group-toggle wide" data-field-wrap="${gid}"><div class="field-label-row"><span class="label-wrap"><span class="field-label" id="${gid}-label">${esc(g.question)}</span>${helpTip("group-help-" + g.path, g.hint_fa)}</span></div><div class="chips" role="radiogroup" aria-labelledby="${gid}-label">${chips(
                gid,
                (i) => `id="${i === (answer === false ? 1 : 0) ? gid : `${gid}-${i}`}" data-group="${g.path}" aria-describedby="group-help-${g.path}"`,
                [[true, "Yes"], [false, "No"]],
                (o) => answer === o,
              )}</div></div>`;
            }
            if (enabled && g.path === "accommodation") {
              const stays = p.data.accommodation || [];
              inner += stays
                .map(
                  (stay, index) =>
                    `<div class="stay-card"><div class="stay-heading"><h3>${icon("bed")}Stay ${index + 1}${stay.city ? " · " + esc(stay.city) : ""}</h3>${stays.length > 1 ? `<button type="button" class="text-button danger-text" data-stay-remove="${index}">${icon("trash")}Remove</button>` : ""}</div><div class="field-grid">${fields
                      .filter((f) => f.stayIndex === index)
                      .map((f) => fieldMarkup(f, p))
                      .join("")}</div></div>`,
                )
                .join("");
              inner += `<button type="button" class="add-button" data-stay-add="true">${icon("plus")}Add another stay</button>`;
            } else if (enabled) inner += `<div class="field-grid">${fields.map((f) => fieldMarkup(f, p)).join("")}</div>`;
          }
          return `<section class="card"><div class="card-heading"><h2>${esc(g.title)}</h2><span class="section-number" title="Field numbers on the official form">${esc(g.number)}</span></div>${inner}</section>`;
        })
        .join("");
    // A short fade when moving between steps; staying on a step re-renders instantly.
    if (lastStep !== p.step) {
      content.classList.remove("step-enter");
      void content.offsetWidth;
      content.classList.add("step-enter");
      lastStep = p.step;
    }
  }
  function refreshField(p, path) {
    const wrap = document.querySelector(`[data-field-wrap="${CSS.escape(path)}"]`),
      f = fieldsFor(p).find((f) => f.path === path);
    if (wrap && f) wrap.outerHTML = fieldMarkup(f, p);
  }
  function renderErrors(p) {
    const errors = session(p).errors;
    $("errors-panel").classList.toggle("hidden", errors.length === 0);
    $("errors-panel").innerHTML =
      `<h2>Let’s check ${errors.length === 1 ? "one detail" : errors.length + " details"}</h2><p class="hint" lang="fa" dir="rtl">برای رفتن به سؤال مربوط روی هر خطا بزنید. اطلاعات ناقص همچنان در مرورگر ذخیره می‌شود.</p>${errors.map((e, i) => `<button type="button" class="error-link" data-error="${i}">${esc(e.path ? fieldsFor(p).find((f) => f.path === e.path)?.label || e.path : "Application")}: ${esc(e.message)} →</button>`).join("")}`;
  }
  function renderReview(p) {
    const show = p.step === 7 && p.view === "form";
    $("review-content").classList.toggle("hidden", !show);
    if (!show) return;
    const count = needsReview(p).length;
    $("review-content").innerHTML =
      `<section class="card"><div class="card-heading"><span class="section-number">FINAL CHECK</span><h2>Your application, at a glance</h2></div><p class="subtitle">${count === 1 ? "1 detail still needs" : count + " details still need"} confirmation. You can generate a clearly named draft.</p><p class="hint" lang="fa" dir="rtl">PDF پیش‌نویس می‌تواند شامل داده نمونه باشد. تأیید سؤال‌ها یعنی مقادیر را با مدارک واقعی تطبیق داده‌اید. خروجی همیشه همان فرم اصلی چهارصفحه‌ای است.</p>${meta.steps
        .map((s, i) => {
          const fields = fieldsFor(p).filter((f) => f.step === i && active(f, p));
          return fields.length
            ? `<details class="review-section" ${compact() ? "" : "open"}><summary><h3>${i + 1}. ${s.title}</h3><button type="button" class="text-button" data-step="${i}">Edit</button></summary><dl>${fields.map((f) => `<div class="review-row"><dt>${esc(f.label)}</dt><dd>${esc(valueText(get(p.data, f.path)))}${needsCheck(p, f.path) ? ` <span class="marker">Check</span>` : ""}</dd></div>`).join("")}</dl></details>`
            : "";
        })
        .join(
          "",
        )}<div class="button-row"><button type="button" class="primary" id="generate" ${context.busy ? "disabled" : ""}>${context.busy ? "Preparing your PDF…" : "Generate " + (isDraft(p) ? "draft " : "") + "PDF →"}</button><button type="button" class="secondary" data-action="validate">Check application</button><button type="button" class="text-button" data-action="export">Export JSON</button></div></section>`;
  }
  let previewKey = null;
  function renderPreview() {
    const p = current();
    if (!p) { previewKey = null; return; }
    const rt = session(p),
      a = rt.artifact;
    const show = Boolean(a && p.step === 7 && p.view === "form");
    const key = JSON.stringify([p.id, a?.pdf, rt.page, p.revision, show]);
    if (key === previewKey) return;
    previewKey = key;
    $("preview-content").classList.toggle("hidden", !show);
    if (!show) return;
    const stale = a.revision !== String(p.revision);
    $("preview-content").innerHTML =
      `<div class="preview-heading"><h2>The official form, filled</h2>${!stale ? `<a class="primary" href="${esc(a.pdf)}" download="${esc(a.filename)}">↓ Download ${a.draft ? "draft " : ""}PDF</a>` : ""}</div>${stale ? '<div class="preview-stale">This preview is out of date. Generate again to include your latest changes.</div>' : ""}<p class="image-caption">${a.draft ? "Draft — confirm assumptions and replace fictional values before submission." : "Validation passed. Review all pages before printing."} Four original pages · Print at 100% / Actual Size.</p><div class="preview-tabs" role="group" aria-label="PDF page">${a.pages.map((_, i) => `<button type="button" data-page="${i}" class="${i === rt.page ? "active" : ""}" aria-pressed="${i === rt.page}">Page ${i + 1}</button>`).join("")}</div><img class="pdf-page" src="${esc(a.pages[rt.page])}" alt="Generated application, page ${rt.page + 1}"><p class="image-caption">Preview images expire after 15 minutes or a server restart. Generate again if needed.</p>`;
    const image = $("preview-content").querySelector("img");
    image.onerror = () => {
      image.replaceWith(
        Object.assign(document.createElement("p"), {
          className: "notice",
          textContent: "Preview expired or unavailable. Generate the PDF again.",
        }),
      );
    };
  }
  function render() {
    const p = current();
    for (const el of document.querySelectorAll(".needs-profile, .step-footer, .view-switch"))
      el.classList.toggle("hidden", !p);
    if (!p) {
      previewKey = null;
      $("profiles").innerHTML = "";
      $("steps").innerHTML = "";
      $("form-content").classList.remove("hidden");
      $("step-count").textContent = "YOUR WORKSPACE";
      $("current-name").textContent = "No applicant yet";
      $("progress-detail").textContent = "Add your first applicant";
      $("applicant-avatar").textContent = "+";
      $("step-title").textContent = "A fresh start.";
      $("step-subtitle").textContent =
        "Create an applicant or import a JSON draft.";
      $("form-content").innerHTML =
        '<section class="card empty-state"><h2>Your workspace is ready</h2><p>Add your first applicant to begin. All answers start blank.</p><button class="primary" data-action="new">Add applicant</button> <button class="secondary" data-action="sample">Try with sample data</button> <button class="secondary" data-action="import">Import JSON</button></section>';
      for (const id of [
        "json-content",
        "review-content",
        "preview-content",
        "errors-panel",
      ])
        $(id).classList.add("hidden");
      return;
    }
    $("current-name").textContent = p.name;
    $("step-count").textContent =
      `STEP ${String(p.step + 1).padStart(2, "0")} OF 08 · ${p.name.toUpperCase()}`;
    $("step-title").textContent = meta.steps[p.step].title;
    $("step-subtitle").textContent =
      meta.steps[p.step].subtitle + ". One detail at a time.";
    $("form-view").setAttribute("aria-pressed", p.view === "form");
    $("json-view").setAttribute("aria-pressed", p.view === "json");
    $("form-content").classList.toggle("hidden", p.view !== "form");
    $("json-content").classList.toggle("hidden", p.view !== "json");
    if (p.view === "json") {
      $("json-editor").value = p.jsonText;
      $("json-status").textContent = p.jsonDirty
        ? "Unapplied edits saved in this browser."
        : "This JSON matches the guided form.";
    } else renderForm(p);
    $("footer-caption").innerHTML =
      `<span class="footer-step">Step ${p.step + 1} of ${meta.steps.length}</span><span class="footer-saved"> · saved automatically</span>`;
    $("previous-step").disabled = p.step === 0;
    $("next-step").textContent = p.step === 7 ? "Generate PDF →" : "Continue →";
    $("next-step").disabled = context.busy;
    updateSummary();
    renderErrors(p);
    renderReview(p);
    renderPreview();
  }

  function dialog(title, body, actions) {
    return new Promise((resolve) => {
      const d = $("modal"),
        form = d.querySelector("form");
      $("modal-title").textContent = title;
      $("modal-body").innerHTML = body;
      $("modal-actions").innerHTML = actions
        .map(
          (a) =>
            `<button type="${a.kind === "primary" ? "submit" : "button"}" value="${esc(a.value)}" class="${esc(a.kind || "secondary")}">${esc(a.label)}</button>`,
        )
        .join("");
      const close = (value) => d.close(value);
      d.querySelector(".dialog-heading button").onclick = () => close("cancel");
      for (const button of $("modal-actions").querySelectorAll(
        'button[type="button"]',
      ))
        button.onclick = () => close(button.value);
      form.onsubmit = (event) => {
        event.preventDefault();
        const action =
          event.submitter ||
          $("modal-actions").querySelector('button[type="submit"]');
        if (!action) return;
        const input = $("modal-input");
        if (input && !input.value.trim()) {
          input.setCustomValidity("Enter a profile name.");
          input.reportValidity();
          return;
        }
        close(action.value);
      };
      const input = $("modal-input");
      if (input) input.oninput = () => input.setCustomValidity("");
      d.returnValue = "cancel";
      d.onclose = () => {
        resolve({ value: d.returnValue, input: $("modal-input")?.value });
        d.onclose = null;
      };
      d.showModal();
      setTimeout(() => input?.focus(), 0);
    });
  }

  return { notify, dialog, render, updateSummary, renderPreview, renderReview, renderErrors, refreshField };
}
