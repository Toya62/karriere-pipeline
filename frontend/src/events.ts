/** Global event bus for Karriere Pipeline frontend. */

export const PIPELINE_EVENTS = {
  APPLICATION_GENERATED: "pipeline:application-generated",
  STATUS_UPDATED: "pipeline:status-updated",
  GENERATION_REQUESTED: "pipeline:generation-requested",
  JOBS_CACHE_INVALIDATED: "pipeline:jobs-cache-invalidated",
} as const;

export interface ApplicationGeneratedDetail {
  company?: string;
  position?: string;
  taskKey?: string;
  cvPath?: string;
  coverPath?: string;
}

export interface GenerationRequestedDetail {
  job: {
    company: string;
    title: string;
    job_url?: string | null;
    location?: string | null;
    description?: string | null;
  };
  tab?: "application" | "email";
}

/** Emit event when generation is requested from another view (e.g. CRM). */
export function requestGeneration(detail: GenerationRequestedDetail): void {
  if (typeof window === "undefined") return;
  window.dispatchEvent(
    new CustomEvent(PIPELINE_EVENTS.GENERATION_REQUESTED, { detail })
  );
}

/** Subscribe to generation requests. */
export function onGenerationRequested(
  handler: (detail: GenerationRequestedDetail) => void
): () => void {
  if (typeof window === "undefined") return () => {};
  const listener = (event: Event) => {
    const custom = event as CustomEvent<GenerationRequestedDetail>;
    if (custom.detail) handler(custom.detail);
  };
  window.addEventListener(PIPELINE_EVENTS.GENERATION_REQUESTED, listener);
  return () => window.removeEventListener(PIPELINE_EVENTS.GENERATION_REQUESTED, listener);
}

/** Emit event when an application generation completes. */
export function notifyApplicationGenerated(detail?: ApplicationGeneratedDetail): void {
  if (typeof window === "undefined") return;
  window.dispatchEvent(
    new CustomEvent(PIPELINE_EVENTS.APPLICATION_GENERATED, { detail })
  );
}

/** Subscribe to application generation completion events. Returns an unsubscribe function. */
export function onApplicationGenerated(
  handler: (detail?: ApplicationGeneratedDetail) => void
): () => void {
  if (typeof window === "undefined") return () => {};
  const listener = (event: Event) => {
    const custom = event as CustomEvent<ApplicationGeneratedDetail>;
    handler(custom.detail);
  };
  window.addEventListener(PIPELINE_EVENTS.APPLICATION_GENERATED, listener);
  return () => window.removeEventListener(PIPELINE_EVENTS.APPLICATION_GENERATED, listener);
}

/** Emit event to invalidate all in-memory jobs cache. */
export function invalidateJobsCache(): void {
  if (typeof window === "undefined") return;
  window.dispatchEvent(new CustomEvent(PIPELINE_EVENTS.JOBS_CACHE_INVALIDATED));
}

/** Subscribe to jobs cache invalidation events. */
export function onJobsCacheInvalidated(handler: () => void): () => void {
  if (typeof window === "undefined") return () => {};
  const listener = () => handler();
  window.addEventListener(PIPELINE_EVENTS.JOBS_CACHE_INVALIDATED, listener);
  return () => window.removeEventListener(PIPELINE_EVENTS.JOBS_CACHE_INVALIDATED, listener);
}
