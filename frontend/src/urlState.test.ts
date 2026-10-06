import { describe, expect, it } from "vitest";

import { DEFAULT_STATE, parseState, serializeState, urlForState } from "./urlState";

describe("parseState", () => {
  it("returns defaults for an empty query", () => {
    expect(parseState("")).toEqual(DEFAULT_STATE);
  });

  it("reads valid values", () => {
    const state = parseState("?dataset=linkedin&q=python&sort=title&dir=asc&page=3&pageSize=25");
    expect(state.dataset).toBe("linkedin");
    expect(state.q).toBe("python");
    expect(state.sort).toBe("title");
    expect(state.dir).toBe("asc");
    expect(state.page).toBe(3);
    expect(state.pageSize).toBe(25);
  });

  it("falls back on invalid enum and numeric values", () => {
    const state = parseState("?sort=bogus&dir=sideways&layout=3d&page=-4&pageSize=zero&date=99y");
    expect(state.sort).toBe(DEFAULT_STATE.sort);
    expect(state.dir).toBe(DEFAULT_STATE.dir);
    expect(state.layout).toBe(DEFAULT_STATE.layout);
    expect(state.page).toBe(DEFAULT_STATE.page);
    expect(state.pageSize).toBe(DEFAULT_STATE.pageSize);
    expect(state.date).toBe(DEFAULT_STATE.date);
  });
});

describe("serializeState", () => {
  it("omits default values", () => {
    expect(serializeState(DEFAULT_STATE)).toBe("");
  });

  it("round-trips a non-default state", () => {
    const state = {
      ...DEFAULT_STATE,
      dataset: "indeed",
      q: "c++",
      loc: "Berlin",
      date: "7d" as const,
      exact: "2026-10-01",
      sort: "company" as const,
      dir: "asc" as const,
      layout: "cards" as const,
      page: 2,
    };
    const roundTripped = parseState(serializeState(state));
    expect(roundTripped).toEqual(state);
  });
});

describe("urlForState", () => {
  it("returns the bare path when state is default", () => {
    expect(urlForState(DEFAULT_STATE, "/app/")).toBe("/app/");
  });

  it("appends a query string when state differs", () => {
    expect(urlForState({ ...DEFAULT_STATE, q: "dev" }, "/app/")).toBe("/app/?q=dev");
  });
});
