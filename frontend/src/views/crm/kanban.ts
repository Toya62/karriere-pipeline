import type { TrackerRecord } from "../../api/types";
import { showToast } from "../../ui/toast";
import { escapeHtml } from "../../utils";
import { crmJobKey } from "./columns";

export interface KanbanColumnMeta {
  id: string;
  title: string;
  subtitle: string;
  targetStatus: string;
  statuses: readonly string[];
  dotVariant: "neutral" | "accent" | "warning" | "success" | "error";
  emptyIcon: string;
  emptyTitle: string;
  emptyDesc: string;
}

export const KANBAN_COLUMNS: readonly KanbanColumnMeta[] = [
  {
    id: "prepared",
    title: "Prepared",
    subtitle: "Drafted & ready",
    targetStatus: "Prepared",
    statuses: ["prepared", "draft", "not applied", ""],
    dotVariant: "neutral",
    emptyIcon: "📥",
    emptyTitle: "Nothing prepared",
    emptyDesc: "Applications ready to submit will appear here.",
  },
  {
    id: "applied",
    title: "Applied",
    subtitle: "Submitted · waiting",
    targetStatus: "Applied",
    statuses: ["applied", "sent"],
    dotVariant: "accent",
    emptyIcon: "🚀",
    emptyTitle: "No active submissions",
    emptyDesc: "Submitted applications awaiting company response.",
  },
  {
    id: "interview",
    title: "Interview",
    subtitle: "Conversations active",
    targetStatus: "Interview",
    statuses: ["interview", "interviewed", "screening", "assessment"],
    dotVariant: "warning",
    emptyIcon: "🎯",
    emptyTitle: "No interviews yet",
    emptyDesc: "Move applications here when recruiters schedule talks.",
  },
  {
    id: "offer",
    title: "Offer",
    subtitle: "Offers & contracts",
    targetStatus: "Offer",
    statuses: ["offer", "accepted"],
    dotVariant: "success",
    emptyIcon: "🏆",
    emptyTitle: "No offers yet",
    emptyDesc: "Offers received and accepted will land here.",
  },
  {
    id: "rejected",
    title: "Rejected",
    subtitle: "Archived & closed",
    targetStatus: "Rejected",
    statuses: ["rejected", "rejected-by-employer", "declined"],
    dotVariant: "error",
    emptyIcon: "📁",
    emptyTitle: "No rejections",
    emptyDesc: "Archived or declined applications appear here.",
  },
];

export function getDaysInStage(dateIso: string | null | undefined): number {
  if (!dateIso) return 0;
  const parsed = Date.parse(dateIso);
  if (Number.isNaN(parsed)) return 0;
  return Math.max(0, Math.floor((Date.now() - parsed) / 86400_000));
}

export async function moveCardOptimistic(
  records: TrackerRecord[],
  recordIndex: number,
  nextStatus: string,
  patchFn: (rec: TrackerRecord, status: string) => Promise<unknown>,
  onRender: () => void
): Promise<boolean> {
  const rec = records[recordIndex];
  if (!rec) return false;
  const prevStatus = rec.status || "Prepared";
  if (prevStatus.toLowerCase() === nextStatus.toLowerCase()) return true;

  // 1. Optimistic update
  rec.status = nextStatus;
  onRender();

  // 2. Background API PATCH
  try {
    await patchFn(rec, nextStatus);
    showToast({
      message: `Moved ${rec.company} to ${nextStatus}.`,
      actionLabel: "Undo",
      onAction: () => {
        void moveCardOptimistic(records, recordIndex, prevStatus, patchFn, onRender);
      },
    });
    return true;
  } catch {
    // 3. Rollback on failure
    rec.status = prevStatus;
    onRender();
    showToast({
      message: `Couldn't move ${rec.company} to ${nextStatus} — reverted.`,
      variant: "error",
      actionLabel: "Retry",
      onAction: () => {
        void moveCardOptimistic(records, recordIndex, nextStatus, patchFn, onRender);
      },
    });
    return false;
  }
}

export function renderKanbanColumnHead(meta: KanbanColumnMeta, count: number): HTMLElement {
  const head = document.createElement("div");
  head.className = "kjc-kanban-col-head";
  head.innerHTML = `
    <div class="kjc-kanban-col-title-group">
      <span class="kjc-status-dot ${meta.dotVariant}" aria-hidden="true"></span>
      <span class="kjc-kanban-col-title">${escapeHtml(meta.title)}</span>
      <span class="kjc-kanban-count" aria-label="${count} applications">${count}</span>
    </div>
    <div class="kjc-kanban-col-subtitle">${escapeHtml(meta.subtitle)}</div>
  `;
  return head;
}

export function renderKanbanEmptyState(meta: KanbanColumnMeta): HTMLElement {
  const empty = document.createElement("div");
  empty.className = "kjc-kanban-empty";
  empty.innerHTML = `
    <div class="kjc-kanban-empty-icon" aria-hidden="true">${meta.emptyIcon}</div>
    <div class="kjc-kanban-empty-title">${escapeHtml(meta.emptyTitle)}</div>
    <div class="kjc-kanban-empty-desc">${escapeHtml(meta.emptyDesc)}</div>
  `;
  return empty;
}

export interface RenderKanbanCardOptions {
  record: TrackerRecord;
  columnId: string;
  statusOptions: readonly string[];
  onOpenDrawer: (record: TrackerRecord) => void;
  onStatusChange: (record: TrackerRecord, newStatus: string) => void;
  onApplyClick?: (record: TrackerRecord) => void;
  onDownloadZip?: (record: TrackerRecord) => void;
}

export function renderKanbanCard(options: RenderKanbanCardOptions): HTMLElement {
  const {
    record,
    columnId,
    statusOptions,
    onOpenDrawer,
    onStatusChange,
    onApplyClick,
    onDownloadZip,
  } = options;

  const card = document.createElement("div");
  card.className = "kjc-kanban-card";
  card.setAttribute("role", "listitem");
  card.draggable = true;

  const key = crmJobKey(record);
  card.addEventListener("dragstart", (e) => {
    e.dataTransfer?.setData("text/plain", key);
    card.classList.add("dragging");
  });
  card.addEventListener("dragend", () => {
    card.classList.remove("dragging");
  });

  const dateStr = record.date_applied ? record.date_applied.slice(0, 10) : "";
  const daysInStage = getDaysInStage(record.date_applied);
  const isStale = columnId === "applied" && daysInStage >= 14;
  const initial = (record.company || "?").trim().charAt(0).toUpperCase();

  const rawCv = String(record.cv_pdf_path || "").replace(/^\/+/, "");
  const cvUrl = record.id
    ? `/api/applications/${record.id}/download?type=cv`
    : (record.cv_pdf_path ? `/${rawCv}?download=1` : "");
  const rawCl = String(record.cover_pdf_path || "").replace(/^\/+/, "");
  const clUrl = record.id
    ? `/api/applications/${record.id}/download?type=cover`
    : (record.cover_pdf_path ? `/${rawCl}?download=1` : "");
  const zipUrl = record.id ? `/api/applications/${record.id}/download?type=zip` : "";

  const currentStatus = (record.status || "Prepared").trim();

  card.innerHTML = `
    <div class="kjc-card-top">
      <div class="kjc-card-company-group">
        <span class="kjc-row-avatar" aria-hidden="true">${escapeHtml(initial)}</span>
        <div class="kjc-card-company" title="${escapeHtml(record.company || "")}">${escapeHtml(record.company || "Unknown")}</div>
      </div>
      <div class="kjc-card-top-right">
        ${isStale ? `<span class="kjc-card-stale" title="In stage for ${daysInStage} days">⚠️ ${daysInStage}d</span>` : (daysInStage > 0 ? `<span class="kjc-card-days">${daysInStage}d</span>` : "")}
        <span class="kjc-card-drag-handle" title="Drag to reorder or change stage" aria-hidden="true">⋮⋮</span>
      </div>
    </div>
    <div class="kjc-card-role" title="${escapeHtml(record.position || "")}">${escapeHtml(record.position || "Untitled Position")}</div>
    <div class="kjc-card-meta">
      ${record.location ? `<span class="kjc-meta-chip"><span class="kjc-meta-icon" aria-hidden="true">📍</span> ${escapeHtml(record.location)}</span>` : ""}
      ${dateStr ? `<span class="kjc-meta-chip"><span class="kjc-meta-icon" aria-hidden="true">📅</span> ${escapeHtml(dateStr)}</span>` : ""}
    </div>
    ${record.notes ? `<div class="kjc-card-notes" title="${escapeHtml(record.notes)}">${escapeHtml(record.notes)}</div>` : ""}
    <div class="kjc-card-footer">
      <div class="kjc-card-links">
        ${record.job_url ? `<a href="${escapeHtml(record.job_url)}" target="_blank" rel="noopener noreferrer" class="kjc-card-pill kjc-pill-apply" title="Open job application URL">Apply ↗</a>` : ""}
        ${cvUrl ? `<a href="${cvUrl}" target="_blank" rel="noopener noreferrer" class="kjc-card-pill" title="View CV">📄 CV</a>` : ""}
        ${clUrl ? `<a href="${clUrl}" target="_blank" rel="noopener noreferrer" class="kjc-card-pill" title="View Cover Letter">📝 Cover</a>` : ""}
        ${zipUrl ? `<a href="${zipUrl}" class="kjc-card-pill kjc-pill-zip" title="Download ZIP Package">📦 ZIP</a>` : ""}
      </div>
      <select class="kjc-card-status-select" aria-label="Move ${escapeHtml(record.company || "")} to stage">
        ${statusOptions.map((opt) => `<option value="${opt}" ${currentStatus.toLowerCase() === opt.toLowerCase() ? "selected" : ""}>${opt}</option>`).join("")}
      </select>
    </div>
  `;

  card.addEventListener("click", (e) => {
    const target = e.target as HTMLElement;
    if (target.closest("select") || target.closest("a") || target.classList.contains("kjc-card-drag-handle")) return;
    onOpenDrawer(record);
  });

  const applyLink = card.querySelector<HTMLAnchorElement>(".kjc-pill-apply");
  if (applyLink && onApplyClick) {
    applyLink.addEventListener("click", () => {
      onApplyClick(record);
    });
  }

  const zipLink = card.querySelector<HTMLAnchorElement>(".kjc-pill-zip");
  if (zipLink && onDownloadZip) {
    zipLink.addEventListener("click", (e) => {
      e.preventDefault();
      onDownloadZip(record);
    });
  }

  const selectEl = card.querySelector<HTMLSelectElement>(".kjc-card-status-select");
  if (selectEl) {
    selectEl.addEventListener("change", (ev) => {
      ev.stopPropagation();
      onStatusChange(record, selectEl.value);
    });
  }

  return card;
}
