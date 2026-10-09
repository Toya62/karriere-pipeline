/** Global event bus for Karriere Pipeline frontend. */

export const PIPELINE_EVENTS = {
  APPLICATION_GENERATED: "pipeline:application-generated",
  STATUS_UPDATED: "pipeline:status-updated",
} as const;

export interface ApplicationGeneratedDetail {
  company?: string;
  position?: string;
  taskKey?: string;
}

/** Emit event when an application generation completes. */
export function notifyApplicationGenerated(detail?: ApplicationGeneratedDetail): void {
  window.dispatchEvent(
    new CustomEvent(PIPELINE_EVENTS.APPLICATION_GENERATED, { detail })
  );
}

/** Subscribe to application generation completion events. Returns an unsubscribe function. */
export function onApplicationGenerated(
  handler: (detail?: ApplicationGeneratedDetail) => void
): () => void {
  const listener = (event: Event) => {
    const custom = event as CustomEvent<ApplicationGeneratedDetail>;
    handler(custom.detail);
  };
  window.addEventListener(PIPELINE_EVENTS.APPLICATION_GENERATED, listener);
  return () => window.removeEventListener(PIPELINE_EVENTS.APPLICATION_GENERATED, listener);
}
