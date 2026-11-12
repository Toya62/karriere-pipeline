export type ThemeMode = "dark" | "light";

const THEME_STORAGE_KEY = "kjc_theme";

function applyTheme(mode: ThemeMode): ThemeMode {
  document.documentElement.setAttribute("data-theme", mode);
  if (mode === "dark") {
    document.documentElement.classList.add("dark");
  } else {
    document.documentElement.classList.remove("dark");
  }
  return mode;
}

export function getTheme(): ThemeMode {
  const attr = document.documentElement.getAttribute("data-theme");
  if (attr === "light" || attr === "dark") return attr;
  const saved = localStorage.getItem(THEME_STORAGE_KEY);
  return saved === "light" ? "light" : "dark";
}

export function initTheme(): ThemeMode {
  const saved = localStorage.getItem(THEME_STORAGE_KEY);
  const mode: ThemeMode = saved === "light" ? "light" : "dark";
  return applyTheme(mode);
}

export function toggleTheme(): ThemeMode {
  const next: ThemeMode = getTheme() === "dark" ? "light" : "dark";
  localStorage.setItem(THEME_STORAGE_KEY, next);
  return applyTheme(next);
}
