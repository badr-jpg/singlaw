export type Appearance = "light" | "dark" | "system";
const CHANGE_EVENT = "singlaw:appearance";
let sessionPreference: Appearance | undefined;

export function readAppearance(): Appearance {
  if (sessionPreference) return sessionPreference;
  try {
    const stored = localStorage.getItem("singlaw.theme");
    return stored === "light" || stored === "dark" ? stored : "system";
  } catch {
    return "system";
  }
}

export function subscribeAppearance(listener: () => void) {
  window.addEventListener(CHANGE_EVENT, listener);
  const onStorage = (event: StorageEvent) => {
    if (event.key !== null && event.key !== "singlaw.theme") return;
    try {
      if (event.storageArea !== localStorage) return;
    } catch {
      return;
    }
    sessionPreference = undefined;
    listener();
  };
  window.addEventListener("storage", onStorage);
  return () => {
    window.removeEventListener(CHANGE_EVENT, listener);
    window.removeEventListener("storage", onStorage);
  };
}

export function setAppearance(value: Appearance) {
  try {
    localStorage.setItem("singlaw.theme", value);
    sessionPreference = undefined;
  } catch {
    sessionPreference = value;
    // Keep all menus in sync even when browser storage is unavailable.
  }
  window.dispatchEvent(new Event(CHANGE_EVENT));
}

export function serverAppearance(): Appearance {
  return "system";
}
