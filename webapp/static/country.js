// Remembers, per browser, which Schengen country's application form is being filled.
const KEY = "visafilla.country";

// Regional-indicator emoji built from the ISO code, e.g. "ES" -> Spanish flag.
const flag = (code) =>
  String.fromCodePoint(...[...code].map((c) => 0x1f1e6 + c.charCodeAt(0) - 65));

export function createCountryPicker({ $, esc, countries }) {
  const read = () => {
    try {
      return localStorage.getItem(KEY);
    } catch {
      return null;
    }
  };
  const write = (code) => {
    try {
      localStorage.setItem(KEY, code);
    } catch {
      // Storage can be blocked; the choice then lasts for this visit only.
    }
  };
  const available = (code) => countries.find((c) => c.code === code && c.available) || null;
  let selected = available(read());
  let onReady = null;

  function card(c) {
    const isSelected = selected?.code === c.code;
    return `<button type="button" class="country-card${isSelected ? " selected" : ""}" data-country="${esc(c.code)}" ${c.available ? `aria-pressed="${isSelected}"` : "disabled"}><span class="country-flag" aria-hidden="true">${flag(c.code)}</span><span class="country-name">${esc(c.name)}</span><span class="country-status">${!c.available ? "Coming soon" : isSelected ? "Selected" : "Available"}</span></button>`;
  }
  function renderChip() {
    const chip = $("country-switch");
    chip.classList.toggle("hidden", !selected);
    if (!selected) return;
    chip.innerHTML = `<span class="country-flag" aria-hidden="true">${flag(selected.code)}</span><span>${esc(selected.name)}</span><svg class="icon" aria-hidden="true"><use href="#i-chevron-down"/></svg>`;
    chip.setAttribute("aria-label", `Application country: ${selected.name}. Change country`);
  }
  function open() {
    const ready = countries.filter((c) => c.available),
      soon = countries.filter((c) => !c.available);
    $("country-close").classList.toggle("hidden", !selected);
    $("country-grid").innerHTML =
      `<h3 class="country-group">Available now</h3><div class="country-cards">${ready.map(card).join("")}</div>` +
      (soon.length
        ? `<h3 class="country-group">Coming soon</h3><div class="country-cards">${soon.map(card).join("")}</div>`
        : "");
    $("country-dialog").showModal();
    $("country-grid").querySelector(".country-card:not([disabled])")?.focus({ preventScroll: true });
  }
  function choose(code) {
    const c = available(code);
    if (!c) return;
    selected = c;
    write(c.code);
    renderChip();
    $("country-dialog").close();
    const ready = onReady;
    onReady = null;
    ready?.();
  }

  $("country-grid").addEventListener("click", (event) => {
    const button = event.target.closest("[data-country]");
    if (button && !button.disabled) choose(button.dataset.country);
  });
  $("country-switch").addEventListener("click", open);
  $("country-close").addEventListener("click", () => $("country-dialog").close());
  // On the first visit a country must be chosen before continuing.
  $("country-dialog").addEventListener("cancel", (event) => {
    if (!selected) event.preventDefault();
  });

  return {
    open,
    get selected() {
      return selected;
    },
    // Calls ready() once a country is chosen: immediately when one is remembered.
    start(ready) {
      renderChip();
      if (selected) ready?.();
      else {
        onReady = ready;
        open();
      }
    },
  };
}
