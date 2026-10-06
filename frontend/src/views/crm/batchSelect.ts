/** Batch selection dropdown for CRM view. */

import type { TrackerRecord } from "../../api/types";

export interface BatchAction {
  label: string;
  action: "open" | "copy" | "dismiss" | "export";
  icon?: string;
  requiresSelection: boolean;
}

export const BATCH_ACTIONS: BatchAction[] = [
  { label: "Open Selected Links", action: "open", icon: "↗", requiresSelection: true },
  { label: "Copy Selected", action: "copy", icon: "📋", requiresSelection: true },
  { label: "Dismiss Selected", action: "dismiss", icon: "🗑", requiresSelection: true },
  { label: "Export Selected (CSV)", action: "export", icon: "📥", requiresSelection: true },
];

export function createBatchSelect(
  onAction: (action: BatchAction, selected: TrackerRecord[]) => void,
  getSelected: () => TrackerRecord[],
  onClose: () => void
): HTMLDivElement {
  const container = document.createElement("div");
  container.className = "kjc-batch-dropdown hidden";

  const button = document.createElement("button");
  button.type = "button";
  button.className = "kjc-btn kjc-batch-trigger";
  button.textContent = "Batch Actions ▼";

  const dropdown = document.createElement("div");
  dropdown.className = "kjc-batch-menu hidden";

  BATCH_ACTIONS.forEach((action) => {
    const item = document.createElement("button");
    item.type = "button";
    item.className = "kjc-batch-item";
    item.innerHTML = `<span class="kjc-batch-icon">${action.icon}</span> ${action.label}`;
    item.addEventListener("click", () => {
      const selected = getSelected();
      if (action.requiresSelection && selected.length === 0) {
        return;
      }
      onAction(action, selected);
      onClose();
    });
    dropdown.appendChild(item);
  });

  container.appendChild(button);
  container.appendChild(dropdown);

  button.addEventListener("click", (e) => {
    e.stopPropagation();
    dropdown.classList.toggle("hidden");
  });

  document.addEventListener("click", () => {
    dropdown.classList.add("hidden");
  });

  return container;
}