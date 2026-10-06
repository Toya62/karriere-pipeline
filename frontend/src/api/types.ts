import type { components } from "./schema";

/** Friendly aliases over the generated OpenAPI component types. */
export type JobRecord = components["schemas"]["JobRecord"];
export type ApprovedIndexEntry = components["schemas"]["ApprovedIndexEntry"];
export type DatasetView = string;
export type JobDescriptions = Record<string, string>;
