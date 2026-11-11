import { describe, expect, it } from "vitest";

import {
  extractError,
  isGuestPayload,
  messageFrom,
  parseLogs,
  parseLogStats,
  parseStatus,
  shouldFetchLogs,
  tailLines,
} from "./scraperState";

describe("parseStatus", () => {
  it("reads boolean flags", () => {
    expect(parseStatus({ running: true }).running).toBe(true);
    expect(parseStatus({ is_running: false }).running).toBe(false);
  });

  it("reads status words", () => {
    expect(parseStatus({ status: "Running" }).running).toBe(true);
    expect(parseStatus({ status: "idle" }).running).toBe(false);
  });

  it("returns null for unknown shapes", () => {
    expect(parseStatus(null).running).toBeNull();
    expect(parseStatus("x").running).toBeNull();
    expect(parseStatus({ foo: 1 }).running).toBeNull();
    expect(parseStatus({ status: "weird" }).running).toBeNull();
  });
});

describe("parseLogs", () => {
  it("returns the logs string", () => {
    expect(parseLogs({ success: true, logs: "a\nb" })).toBe("a\nb");
  });

  it("joins array logs and tolerates bad payloads", () => {
    expect(parseLogs({ logs: ["a", "b"] })).toBe("a\nb");
    expect(parseLogs(undefined)).toBe("");
    expect(parseLogs({ logs: 5 })).toBe("");
  });
});

describe("tailLines", () => {
  it("keeps only the last N lines", () => {
    expect(tailLines("1\n2\n3\n4", 2)).toBe("3\n4");
    expect(tailLines("1\n2", 5)).toBe("1\n2");
  });
});

describe("shouldFetchLogs", () => {
  it("polls while running or unknown", () => {
    expect(shouldFetchLogs({ running: true, wasRunning: true, graceTicks: 0 })).toBe(true);
    expect(shouldFetchLogs({ running: null, wasRunning: null, graceTicks: 0 })).toBe(true);
  });

  it("does one final fetch when a run ends", () => {
    expect(shouldFetchLogs({ running: false, wasRunning: true, graceTicks: 0 })).toBe(true);
  });

  it("stays quiet when idle", () => {
    expect(shouldFetchLogs({ running: false, wasRunning: false, graceTicks: 0 })).toBe(false);
  });

  it("polls during the grace window after start", () => {
    expect(shouldFetchLogs({ running: false, wasRunning: false, graceTicks: 2 })).toBe(true);
  });
});

describe("message helpers", () => {
  it("extracts error text from JSON bodies", () => {
    expect(extractError('{"success":false,"error":"Scraper already running"}', "x")).toBe("Scraper already running");
    expect(extractError("not json", "fallback")).toBe("fallback");
  });

  it("extracts success messages", () => {
    expect(messageFrom({ message: "Local scraper started" }, "ok")).toBe("Local scraper started");
    expect(messageFrom({}, "ok")).toBe("ok");
  });
});

describe("parseLogStats & isGuestPayload", () => {
  it("detects guest payload flag", () => {
    expect(isGuestPayload({ guest: true, logs: "" })).toBe(true);
    expect(isGuestPayload({ guest: false, logs: "test" })).toBe(false);
    expect(isGuestPayload(null)).toBe(false);
  });

  it("parses scraper harvest metrics", () => {
    const text = `
      ✓ linkedin: Scraped 14
      ✓ ba: Scraped 22
      Pipeline: 36 approved, 40 scraped
    `;
    const stats = parseLogStats(text);
    expect(stats.scraped).toBe(40);
    expect(stats.approved).toBe(36);
    expect(stats.portalCounts.linkedin).toBe(14);
    expect(stats.portalCounts.ba).toBe(22);
  });
});
