export type ThemeMode = "dark" | "light";

const THEME_STORAGE_KEY = "kjc_theme";

function getSystemTheme(): ThemeMode {
  if (typeof window !== "undefined" && window.matchMedia && window.matchMedia("(prefers-color-scheme: light)").matches) {
    return "light";
  }
  return "dark";
}

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
  if (saved === "light" || saved === "dark") return saved;
  return getSystemTheme();
}

export function initTheme(): ThemeMode {
  const saved = localStorage.getItem(THEME_STORAGE_KEY);
  const mode: ThemeMode = saved === "light" || saved === "dark" ? saved : getSystemTheme();
  
  if (typeof window !== "undefined" && window.matchMedia) {
    const mediaQuery = window.matchMedia("(prefers-color-scheme: dark)");
    mediaQuery.addEventListener("change", (e) => {
      // Only react to OS changes if user hasn't explicitly set preference
      if (!localStorage.getItem(THEME_STORAGE_KEY)) {
        applyTheme(e.matches ? "dark" : "light");
      }
    });
  }

  return applyTheme(mode);
}

export function toggleTheme(): ThemeMode {
  const next: ThemeMode = getTheme() === "dark" ? "light" : "dark";
  localStorage.setItem(THEME_STORAGE_KEY, next);
  return applyTheme(next);
}

