import { describe, expect, it } from "vitest";

import { toCsv } from "@/lib/csv";

describe("toCsv", () => {
  it("writes a BOM, the header and escapes separators, quotes and lists", () => {
    const out = toCsv(["id", "name_ru", "segment_ids", "capacity"], [
      { id: "P1", name_ru: "Насос \"А\", резерв", segment_ids: ["S1", "S2"], capacity: 12.5 },
      { id: "P2", name_ru: null, segment_ids: [], capacity: undefined },
    ]);
    expect(out.startsWith("﻿id,name_ru,segment_ids,capacity\r\n")).toBe(true);
    expect(out).toContain('P1,"Насос ""А"", резерв","S1;S2",12.5\r\n');
    expect(out).toContain("P2,,,\r\n");
  });
});
