export interface ToastOptions {
  message: string;
  actionLabel?: string;
  onAction?: () => void;
  durationMs?: number;
  variant?: "default" | "error" | "success";
}

const toastQueue: ToastOptions[] = [];
let toastActive = false;
let activeTimer: ReturnType<typeof setTimeout> | null = null;

function ensureToastZone(): HTMLElement {
  let zone = document.getElementById("kjc-toast-zone");
  if (!zone) {
    zone = document.createElement("div");
    zone.id = "kjc-toast-zone";
    zone.className = "kjc-toast-zone";
    zone.setAttribute("aria-live", "polite");
    document.body.appendChild(zone);
  }
  return zone;
}

function pumpToasts(): void {
  if (toastActive || toastQueue.length === 0) return;
  toastActive = true;
  const item = toastQueue.shift()!;
  const zone = ensureToastZone();

  const el = document.createElement("div");
  el.className = `kjc-toast${item.variant && item.variant !== "default" ? ` kjc-toast--${item.variant}` : ""}`;
  el.setAttribute("role", "status");

  const span = document.createElement("span");
  span.textContent = item.message;
  el.appendChild(span);

  const dismiss = () => {
    if (activeTimer) {
      clearTimeout(activeTimer);
      activeTimer = null;
    }
    if (el.parentNode) el.parentNode.removeChild(el);
    toastActive = false;
    pumpToasts();
  };

  if (item.actionLabel) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.textContent = item.actionLabel;
    btn.addEventListener("click", () => {
      try {
        item.onAction?.();
      } finally {
        dismiss();
      }
    });
    el.appendChild(btn);
  }

  zone.appendChild(el);
  activeTimer = setTimeout(dismiss, item.durationMs ?? 4500);
}

export function showToast(opts: ToastOptions): void {
  toastQueue.push(opts);
  pumpToasts();
}

export function _resetToastsForTest(): void {
  toastQueue.length = 0;
  toastActive = false;
  if (activeTimer) {
    clearTimeout(activeTimer);
    activeTimer = null;
  }
}
