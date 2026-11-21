import { describe, expect, it } from "vitest";

import { needValueAt, type NeedReading } from "./needs";

const reading = (value: number, ratePerHour: number): NeedReading => ({
  value,
  updated_at: "2026-11-21T12:00:00Z",
  rate_per_hour: ratePerHour,
});

const at = (iso: string) => new Date(iso);

describe("needValueAt", () => {
  it("moves in a straight line at the rate the API gives", () => {
    expect(needValueAt(reading(100, -6), at("2026-11-21T14:30:00Z"))).toBe(85);
  });

  it("stays within 0 and 100", () => {
    expect(needValueAt(reading(10, -7), at("2026-11-21T15:00:00Z"))).toBe(0);
    expect(needValueAt(reading(95, 12), at("2026-11-21T20:00:00Z"))).toBe(100);
  });

  it("keeps the stored value when the device clock is behind the server", () => {
    expect(needValueAt(reading(50, -6), at("2026-11-21T11:00:00Z"))).toBe(50);
  });
});
