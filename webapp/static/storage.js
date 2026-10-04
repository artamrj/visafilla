import { $, clone, syncJSON } from "./helpers.js";

export function createStorage(state) {
  let db, saveTimer, saveCounter = 0;
  function initDB() {
    return new Promise((resolve, reject) => {
      const request = indexedDB.open("visafilla", 2);
      request.onupgradeneeded = () => {
        // One-time reset of the previous workspace, including signatures.
        if (request.result.objectStoreNames.contains("workspace"))
          request.result.deleteObjectStore("workspace");
        request.result.createObjectStore("workspace");
      };
      request.onsuccess = () => {
        const connection = request.result;
        connection.onversionchange = () => {
          connection.close();
          storageFailure(new Error("Reload this tab to continue."));
        };
        resolve(connection);
      };
      request.onerror = () => reject(request.error);
      request.onblocked = () => {
        $("storage-warning").textContent =
          "Close other VisaFilla tabs to finish clearing the old workspace.";
        $("storage-warning").classList.remove("hidden");
      };
    });
  }
  function readState() {
    return new Promise((resolve, reject) => {
      const req = db
        .transaction("workspace")
        .objectStore("workspace")
        .get("current");
      req.onsuccess = () => resolve(req.result);
      req.onerror = () => reject(req.error);
    });
  }
  function storageFailure(error) {
    $("save-status").textContent = "Not saved";
    $("storage-warning").textContent =
      "Browser storage is unavailable. Export JSON before closing this page. " +
      (error?.message || "");
    $("storage-warning").classList.remove("hidden");
  }
  function persist() {
    cancelSave();
    if (!db) {
      storageFailure();
      return Promise.resolve();
    }
    const version = ++saveCounter;
    const snapshot = clone(state);
    for (const p of snapshot.profiles) syncJSON(p);
    $("save-status").textContent = "Saving…";
    return new Promise((resolve) => {
      try {
        const tx = db.transaction("workspace", "readwrite");
        tx.objectStore("workspace").put(snapshot, "current");
        tx.oncomplete = () => {
          if (version === saveCounter)
            $("save-status").textContent = "Saved on this device";
          resolve();
        };
        tx.onerror = () => {
          storageFailure(tx.error);
          resolve();
        };
      } catch (e) {
        storageFailure(e);
        resolve();
      }
    });
  }
  function scheduleSave() {
    $("save-status").textContent = "Unsaved changes";
    clearTimeout(saveTimer);
    saveTimer = setTimeout(persist, 350);
  }

  function cancelSave() { clearTimeout(saveTimer); saveTimer = null; }
  function setDB(connection) { db = connection; return connection; }
  return { initDB, readState, storageFailure, persist, scheduleSave, cancelSave, setDB,
    hasPendingSave: () => saveTimer != null };
}
