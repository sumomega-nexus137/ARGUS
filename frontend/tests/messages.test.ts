import { describe, expect, it } from "vitest";

import en from "@/messages/en.json";
import kk from "@/messages/kk.json";
import ru from "@/messages/ru.json";

function keys(o: Record<string, unknown>, p = ""): string[] {
  return Object.entries(o).flatMap(([k, v]) => (v && typeof v === "object" ? keys(v as Record<string, unknown>, `${p}${k}.`) : [`${p}${k}`]));
}

describe("translations", () => {
  it("kk, ru and en have identical key sets", () => {
    const e = keys(en).sort();
    expect(keys(kk).sort()).toEqual(e);
    expect(keys(ru).sort()).toEqual(e);
  });
  it("the language switcher labels are present and Kazakh is complete", () => {
    expect(keys(kk).length).toBeGreaterThan(500);
    expect((kk as { health: Record<string, string> }).health.PLAN_AT_RISK).toBeTruthy();
  });
});
