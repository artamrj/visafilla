// A short "how it works" guide on the first visit; reopened any time from Help in the sidebar.
const KEY = "visafilla.welcome";

export function createWelcome({ $, onSample }) {
  const dialog = $("welcome-dialog");
  const hidden = () => {
    try {
      return localStorage.getItem(KEY) === "hidden";
    } catch {
      return false;
    }
  };
  const remember = () => {
    try {
      if ($("welcome-hide").checked) localStorage.setItem(KEY, "hidden");
      else localStorage.removeItem(KEY);
    } catch {
      // Storage can be blocked; the guide then shows again next visit.
    }
  };
  function open() {
    $("welcome-hide").checked = hidden() || !dialog.dataset.seen;
    dialog.dataset.seen = "true";
    dialog.showModal();
    $("welcome-start").focus();
  }
  // Save the choice right away; the dialog's own close event (Escape) also saves it.
  const finish = () => {
    remember();
    dialog.close();
  };
  dialog.addEventListener("close", remember);
  $("welcome-start").onclick = finish;
  $("welcome-sample").onclick = () => {
    finish();
    onSample();
  };
  return {
    open,
    maybeShow() {
      if (!hidden()) open();
    },
  };
}
