import { trapFocus } from "./focusTrap";

export interface PaletteItem {
  id: string;
  label: string;
  category: "Navigation" | "Action" | "Record" | "Shortcuts";
  shortcut?: string;
  run: () => void;
}

export interface CommandPaletteHandle {
  open: () => void;
  close: () => void;
  destroy: () => void;
}

function isSubsequence(needle: string, hay: string): boolean {
  const n = needle.toLowerCase();
  const h = hay.toLowerCase();
  let i = 0;
  for (let j = 0; j < h.length && i < n.length; j++) {
    if (h[j] === n[i]) i++;
  }
  return i === n.length;
}

export function createCommandPalette(getItems: () => PaletteItem[]): CommandPaletteHandle {
  const backdrop = document.createElement("div");
  backdrop.className = "kjc-palette-backdrop";
  backdrop.innerHTML = `
    <div class="kjc-palette" role="dialog" aria-modal="true" aria-label="Command palette">
      <input
        id="kjc-palette-input"
        type="text"
        placeholder="Jump to a view, job, or action…"
        autocomplete="off"
        aria-label="Search commands"
      />
      <div class="kjc-palette-list" id="kjc-palette-list" role="listbox"></div>
      <div class="kjc-palette-foot">
        <span><kbd class="kjc-kbd">↑↓</kbd> navigate</span>
        <span><kbd class="kjc-kbd">Enter</kbd> run</span>
        <span><kbd class="kjc-kbd">Esc</kbd> close</span>
      </div>
    </div>
  `;
  document.body.appendChild(backdrop);

  const dialogEl = backdrop.querySelector<HTMLElement>(".kjc-palette")!;
  const input = backdrop.querySelector<HTMLInputElement>("#kjc-palette-input")!;
  const list = backdrop.querySelector<HTMLElement>("#kjc-palette-list")!;

  let filtered: PaletteItem[] = [];
  let selected = 0;
  let releaseFocus: (() => void) | null = null;

  const render = () => {
    list.innerHTML = "";
    if (filtered.length === 0) {
      const empty = document.createElement("div");
      empty.className = "kjc-palette-empty";
      empty.textContent = "No matching commands or views.";
      list.appendChild(empty);
      return;
    }

    filtered.forEach((item, idx) => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = `kjc-palette-item${idx === selected ? " sel" : ""}`;
      btn.setAttribute("role", "option");
      btn.setAttribute("aria-selected", idx === selected ? "true" : "false");

      const cat = document.createElement("span");
      cat.className = "kjc-palette-cat";
      cat.textContent = item.category;

      const label = document.createElement("span");
      label.className = "kjc-palette-label";
      label.textContent = item.label;

      btn.appendChild(cat);
      btn.appendChild(label);

      if (item.shortcut) {
        const sc = document.createElement("kbd");
        sc.className = "kjc-kbd";
        sc.textContent = item.shortcut;
        btn.appendChild(sc);
      }

      btn.addEventListener("click", () => runItem(item));
      btn.addEventListener("mousemove", () => {
        if (selected !== idx) {
          selected = idx;
          render();
        }
      });

      list.appendChild(btn);
    });
  };

  const close = () => {
    backdrop.classList.remove("open");
    releaseFocus?.();
    releaseFocus = null;
  };

  const runItem = (item: PaletteItem) => {
    close();
    item.run();
  };

  const open = () => {
    filtered = getItems();
    selected = 0;
    input.value = "";
    backdrop.classList.add("open");
    render();
    releaseFocus = trapFocus(dialogEl);
    setTimeout(() => input.focus(), 0);
  };

  input.addEventListener("input", () => {
    const q = input.value.trim();
    const all = getItems();
    filtered = q
      ? all.filter((it) => isSubsequence(q, `${it.category} ${it.label}`))
      : all;
    selected = 0;
    render();
  });

  input.addEventListener("keydown", (e) => {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      selected = Math.min(selected + 1, Math.max(0, filtered.length - 1));
      render();
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      selected = Math.max(selected - 1, 0);
      render();
    } else if (e.key === "Enter") {
      e.preventDefault();
      if (filtered[selected]) runItem(filtered[selected]);
    } else if (e.key === "Escape") {
      e.preventDefault();
      close();
    }
  });

  backdrop.addEventListener("click", (e) => {
    if (e.target === backdrop) close();
  });

  const destroy = () => {
    close();
    backdrop.remove();
  };

  return { open, close, destroy };
}
