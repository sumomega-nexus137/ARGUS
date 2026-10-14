import { describe, expect, it } from "vitest";

import { countdown, dateTime, hhmm, num, pickName, relHHMM } from "@/lib/format";

describe("format", () => {
  it("formats times in the area offset, not the browser timezone", () => {
    expect(hhmm("2026-04-12T05:00:00Z", 300)).toBe("10:00");
    expect(dateTime("2026-04-12T21:30:00Z", 300)).toBe("13.04.2026 02:30");
    expect(relHHMM("2026-04-12T05:00:00Z", 235.9, 300)).toBe("13:55");
  });
  it("never renders undefined / NaN / Infinity", () => {
    expect(hhmm(null, 300)).toBe("—");
    expect(relHHMM("2026-04-12T05:00:00Z", Infinity, 300)).toBe("—");
    expect(countdown(undefined)).toBe("—");
    expect(num(NaN)).toBe("—");
  });
  it("countdown shows overdue with a minus sign", () => {
    expect(countdown(154)).toBe("02:34");
    expect(countdown(-7)).toBe("−00:07");
  });
  it("falls back through multilingual names", () => {
    expect(pickName({ kk: null, ru: "Атбасар", en: "Atbasar" }, "kk")).toBeTruthy();
    expect(pickName({ en: "Atbasar" }, "en")).toBe("Atbasar");
    expect(pickName(null, "kk")).toBe("—");
  });
});
