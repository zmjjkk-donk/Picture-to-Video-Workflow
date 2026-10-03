import source from "./App.tsx?raw";
import { describe, expect, it } from "vitest";
import { businessContract } from "./test/businessContract";
import baseline from "./test/v5-business-baseline.json";

describe("V5 business preservation", () => {
  it("preserves original requests, state, form conditions, links and event bindings", () => {
    expect(businessContract(source)).toEqual(baseline);
  });
});
