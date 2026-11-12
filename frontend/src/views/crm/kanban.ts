import type { TrackerRecord } from "../../api/types";
import { showToast } from "../../ui/toast";

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

