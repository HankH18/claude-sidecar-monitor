import { afterEach, describe, expect, it } from "vitest";
import { _resetApiTokenCacheForTests, getApiToken } from "./token";

function setMeta(content: string | null) {
  for (const n of document.querySelectorAll('meta[name="csm-token"]')) {
    n.remove();
  }
  if (content !== null) {
    const m = document.createElement("meta");
    m.setAttribute("name", "csm-token");
    m.setAttribute("content", content);
    document.head.appendChild(m);
  }
  _resetApiTokenCacheForTests();
}

describe("getApiToken", () => {
  afterEach(() => setMeta(null));

  it("reads the value from a meta[name='csm-token'] tag", () => {
    setMeta("secret-abc");
    expect(getApiToken()).toBe("secret-abc");
  });

  it("treats the literal __CSM_TOKEN__ placeholder as empty", () => {
    setMeta("__CSM_TOKEN__");
    expect(getApiToken()).toBe("");
  });

  it("returns empty string when no meta tag is present", () => {
    setMeta(null);
    expect(getApiToken()).toBe("");
  });
});
